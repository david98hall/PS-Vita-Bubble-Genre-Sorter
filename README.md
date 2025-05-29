# PS Vita Bubble Genre Sorter
This is a script for sorting your PS Vita game bubbles into genre folders alphabetically.

## Genre Retrieval
The genres are retrieved from GiantBomb using their API if possible. This is done by searching for the bubble title to get the GiantBomb game GUID and then get the genres using that.
Since GiantBomb does not have PS Vita titleIds, this will not be perfect as the genre retrieval depends on the search of the game title being accurate.
This means that the genre might not be accurate for some bubbles.

### Choice of Database
The reason for using GiantBomb as the genre source is that their API is free to use and that their game genres seemed good (subjectively).
Other sources, such as Renascene, had bad genre names, no APIs (thus needed web scraping), and were unstable. Moby Games was also considered but their API is not free to use.

### Limitations
The thread sleeps between each genre API request because GiantBomb's API has a request per second limit and might temporarily block your usage otherwise.
There is also a request per hour limit. This means that the API requests might fail if you have too many games.

## How To Use
1. Rebuild your PS Vita database in order to remove exising folders.
2. Transfer your app.db file (located in the ur0:shell/db directory on your PS Vita) to your computer, next to the Python script.
3. Create a file called giantbomb_api containing your GiantBomb API key in the same directory as the script.
4. Run the sort_bubbles_into_genres.py script. A genre_dict.pkl file is created containing your games, sorted into genres. This is done so that you do not have to fetch from the API again if you want to run the script again.
5. Overwrite the existing app.db file in ur0:shell/db on your PS Vita with the one on your computer.
6. Restart your PS Vita

## After Running The Script
When you have run the script, you will notice that the created folders have no icons. Bubbles might also be missing their icons as well and might appear white.
To resolve these issues, click on each bubble to restore their icon and then for each folder, move one icon, move it back and then close the folder.
The latter will generate new folder icons in .dds format and store them in the reserved05 column in tbl_appinfo_icon as binary blobs on the folder icon rows.
