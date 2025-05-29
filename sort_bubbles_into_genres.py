#!/usr/bin/env python3

import sqlite3
from collections import defaultdict
from math import ceil
import pickle
from genre_retrieval import get_icon_genre, get_genre_mappings, get_genre_weights

def reorganise_app_db(db_path: str = "app.db") -> None:
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()

    try:
        # Fetch all icon rows
        cur.execute("SELECT * FROM tbl_appinfo_icon")
        icons = cur.fetchall()
        icon_cols = [d[0] for d in cur.description]
        icon_idx  = {c: i for i, c in enumerate(icon_cols)}

        genre_dict = get_genre_dict(icons, icon_idx)

        # Sort the genres and the titles within each genre alphabetically
        for rows in genre_dict.values():
            rows.sort(key=lambda r: r[icon_idx['title']])
        sorted_genres = sorted(genre_dict)

        cur.execute("PRAGMA table_info(tbl_appinfo_page)")
        page_cols = [row[1] for row in cur.fetchall()]

        # Get the new icon and page rows
        new_icon_rows, new_page_rows, folder_icon_page_id, folder_icon_pos = get_new_rows(genre_dict, sorted_genres, icon_idx, icon_cols, page_cols)
        
        # Re-create tables in *temp* versions identical to originals
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tbl_appinfo_icon'")
        create_icon_sql = cur.fetchone()[0]
        cur.execute("DROP TABLE IF EXISTS tbl_appinfo_icon_temp")
        cur.execute(create_icon_sql.replace("tbl_appinfo_icon", "tbl_appinfo_icon_temp", 1))

        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tbl_appinfo_page'")
        create_page_sql = cur.fetchone()[0]
        cur.execute("DROP TABLE IF EXISTS tbl_appinfo_page_temp")
        cur.execute(create_page_sql.replace("tbl_appinfo_page", "tbl_appinfo_page_temp", 1))

        # Fetch the row with the titleId "VITASHELL"
        # This icon should not be placed in a folder in case anything goes wrong, then it can still be launced from the LiveArea
        cur.execute("SELECT * FROM tbl_appinfo_icon WHERE titleId = ?", ("VITASHELL",))
        vitashell_row = list(cur.fetchone())

        # Update pageId and pos values to place VITASHELL after all folders
        vitashell_row[icon_idx['pageId']] = folder_icon_page_id + 1 if folder_icon_pos == 9 else folder_icon_page_id
        vitashell_row[icon_idx['pos']] = folder_icon_pos if folder_icon_pos < 9 else 0

        # Replace the row with titleId == "VITASHELL" in new_icon_rows
        for i, row in enumerate(new_icon_rows):
            if row[icon_idx['titleId']] == "VITASHELL":
                new_icon_rows[i] = tuple(vitashell_row)
                break

        # Bulk-insert new rows
        cur.execute("DELETE FROM tbl_appinfo_icon_temp")
        icon_q = f"INSERT INTO tbl_appinfo_icon_temp ({', '.join(icon_cols)}) VALUES ({', '.join('?'*len(icon_cols))})"
        cur.executemany(icon_q, new_icon_rows)

        cur.execute("DELETE FROM tbl_appinfo_page_temp")
        page_q = f"INSERT INTO tbl_appinfo_page_temp ({', '.join(page_cols)}) VALUES ({', '.join('?'*len(page_cols))})"
        cur.executemany(page_q, new_page_rows)

        # Swap temp tables into place
        cur.execute("DROP TABLE tbl_appinfo_icon")
        cur.execute("ALTER TABLE tbl_appinfo_icon_temp RENAME TO tbl_appinfo_icon")

        cur.execute("DROP TABLE tbl_appinfo_page")
        cur.execute("ALTER TABLE tbl_appinfo_page_temp RENAME TO tbl_appinfo_page")

        # Create indexes for optimized queries
        cur.execute("CREATE INDEX idx_icon_pos ON tbl_appinfo_icon (pos, pageId)")
        cur.execute("CREATE INDEX idx_icon_title ON tbl_appinfo_icon (title, titleId, type)")
        cur.execute("CREATE INDEX idx_page_no ON tbl_appinfo_page (pageNo)")

        # Create triggers for page management
        cur.execute("""
        CREATE TRIGGER tgr_deletePage2 
        AFTER DELETE ON tbl_appinfo_page 
        WHEN OLD.pageNo >= 0 
        BEGIN 
            UPDATE tbl_appinfo_page 
            SET pageNo = pageNo - 1 
            WHERE tbl_appinfo_page.pageNo > OLD.pageNo; 
        END
        """)

        cur.execute("""
        CREATE TRIGGER tgr_insertPage2 
        BEFORE INSERT ON tbl_appinfo_page 
        WHEN NEW.pageNo >= 0 
        BEGIN 
            UPDATE tbl_appinfo_page 
            SET pageNo = pageNo + 1 
            WHERE tbl_appinfo_page.pageNo >= NEW.pageNo; 
        END
        """)

        conn.commit()
        print("✅  All icons neatly sorted into alphabetic genre folders!")

    except Exception as exc:
        conn.rollback()
        print(f"❌  Error: {exc}")

    finally:
        conn.close()

def get_new_rows(genre_dict: dict[str, list[tuple]], sorted_genres: list[str], icon_idx: dict[str, int], icon_cols, page_cols) -> tuple[list[tuple], list[tuple], int, int]:

    max_num_icons_per_page = 10

    # How many folder icons and pages are needed?
    total_folders = sum(ceil(len(rows) / max_num_icons_per_page) for rows in genre_dict.values())
    folder_icon_pages = ceil(total_folders / max_num_icons_per_page)

    page_idx  = {c: i for i, c in enumerate(page_cols)}

    def make_page_row(page_id: int, page_no: int) -> tuple:
        """Return a tuple matching tbl_appinfo_page columns."""
        row = [None] * len(page_cols)
        if 'pageId'         in page_idx: row[page_idx['pageId']]        = page_id
        if 'pageNo'         in page_idx: row[page_idx['pageNo']]        = -100000000 if page_id == 1 else page_no
        if 'bgColor'        in page_idx: row[page_idx['bgColor']]       = 0
        if 'texWidth'       in page_idx: row[page_idx['texWidth']]      = 0
        if 'texHeight'      in page_idx: row[page_idx['texHeight']]     = 0
        if 'imageWidth'     in page_idx: row[page_idx['imageWidth']]    = 0
        if 'imageHeight'    in page_idx: row[page_idx['imageHeight']]   = 0
        if 'reserved01'     in page_idx: row[page_idx['reserved01']]    = 33554431
        return tuple(row)

    # Build new rows for pages and icons
    new_page_rows: list[tuple] = []
    new_icon_rows: list[tuple] = []

    # Regular pages that will hold folder icons
    regular_page_offset = 2  # first regular page starts at pageId == 2, pageId == 1 corresponds to hidden icons
    for pid in range(1, folder_icon_pages + regular_page_offset):
        new_page_rows.append(make_page_row(pid, pid - regular_page_offset))

    folder_counter = 0
    next_folder_page_id = folder_icon_pages + regular_page_offset
    next_folder_page_no = -10000001 # The pageNo for a folder starts with -1, followed by 7 digits

    folder_icon_pos = 0
    folder_icon_page_id = regular_page_offset

    for genre in sorted_genres:
        rows = genre_dict[genre]

        folder_counter = 0
        for chunk_start in range(0, len(rows), max_num_icons_per_page):
            chunk = rows[chunk_start:chunk_start + max_num_icons_per_page]

            # Create the folder page (negative pageNo)
            folder_page_id = next_folder_page_id
            folder_page_no = next_folder_page_no
            new_page_rows.append(make_page_row(folder_page_id, folder_page_no))
            next_folder_page_id += 1
            next_folder_page_no -= 1

            # Move the 10 (or fewer) app icons into that folder page
            for pos, icon in enumerate(chunk):
                icon = list(icon)
                icon[icon_idx['pageId']] = folder_page_id
                icon[icon_idx['pos']]    = pos
                new_icon_rows.append(tuple(icon))

            # Create the folder icon entry on a regular page
            if folder_icon_pos >= max_num_icons_per_page: # new regular page needed
                folder_icon_page_id += 1
                folder_icon_pos = 0

            folder_num   = folder_counter + 1
            folder_title = f"{genre} {folder_num}"
            folder_tid   = f"__{genre.lower().replace(' ', '_')}_{folder_num}__"

            folder_icon = [None] * len(icon_cols)
            if 'titleId'            in icon_idx: folder_icon[icon_idx['titleId']]           = folder_tid
            if 'title'              in icon_idx: folder_icon[icon_idx['title']]             = folder_title
            if 'type'               in icon_idx: folder_icon[icon_idx['type']]              = 5
            if 'icon0Type'          in icon_idx: folder_icon[icon_idx['icon0Type']]         = 7
            if 'pageId'             in icon_idx: folder_icon[icon_idx['pageId']]            = folder_icon_page_id
            if 'pos'                in icon_idx: folder_icon[icon_idx['pos']]               = folder_icon_pos
            if 'reserved01'         in icon_idx: folder_icon[icon_idx['reserved01']]        = folder_page_no
            if 'status'             in icon_idx: folder_icon[icon_idx['status']]            = 0
            if 'parentalLockLv'     in icon_idx: folder_icon[icon_idx['parentalLockLv']]    = 0

            # Add the folder icon to the new icon rows
            new_icon_rows.append(tuple(folder_icon))

            # Increment values for the next folder icon
            folder_pos_increment = 1
            folder_icon_pos += folder_pos_increment
            folder_counter  += 1

            only_one_genre_folder = folder_counter == 1 and len(new_icon_rows) > 0 and chunk_start + 10 >= len(rows)
            if only_one_genre_folder:
                # If this is the only folder for this genre, remove the " 1" suffix from the title
                last_icon_row = list(new_icon_rows[-1])
                last_icon_row[3] = last_icon_row[3].rstrip(" 1")
                new_icon_rows[-1] = tuple(last_icon_row)
    
    return new_icon_rows, new_page_rows, folder_icon_page_id, folder_icon_pos

def get_genre_dict(icons, icon_idx) -> None:
    # Load genre_dict from file if it exists
    genre_dict_file = "genre_dict.pkl"
    try:
        with open(genre_dict_file, "rb") as f:
            genre_dict: dict[str, list[tuple]] = pickle.load(f)
            print("✅ Loaded genre_dict from file.")

    except FileNotFoundError:
        print("ℹ️ genre_dict file not found. Generating it now.")

        genre_mappings: dict[str, str] = get_genre_mappings()
        genre_weights: dict[str, int] = get_genre_weights()

        # Group icons by genre & sort alphabetically
        genre_dict: dict[str, list[tuple]] = defaultdict(list)
        for row in icons:
            genre = get_icon_genre(row[icon_idx['title']], row[icon_idx['titleId']], genre_mappings, genre_weights)
            genre_dict[genre].append(row)

        # Save genre_dict to file for future use
        with open(genre_dict_file, "wb") as f:
            pickle.dump(genre_dict, f)
            print("✅ Saved genre_dict to file.")
        
    return genre_dict

if __name__ == "__main__":
    reorganise_app_db("app.db")
