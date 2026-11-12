# Commands and skills

You do not need exact wording. These are examples.

## Instant (no AI request)

| Say | What happens |
|---|---|
| "Open notepad", "Launch Chrome" | Opens the program |
| "Close notepad" | Asks the program to close (it can still prompt to save) |
| "Open YouTube", "Go to gmail in Chrome" | Opens the site |
| "Open YouTube and search for lofi beats" | Searches that site |
| "Search for cat videos on YouTube", "Play despacito on YouTube" | Same |
| "Google weather in Lahore", "Search for cheap flights" | Web search |
| "Open my downloads folder" | Opens the folder |
| "Volume up", "Set volume to 40 percent", "Mute" | Volume |
| "Pause the music", "Next song" | Media keys |
| "Take a screenshot" | Saves to Pictures\Screenshots |
| "Lock my PC", "Shut down the computer" | Power (shut down asks first) |
| "Undo that" | Reverses the last file change |
| "What time is it?" | Answers directly |

Sites with built-in search: Google, YouTube, Bing, Wikipedia, Amazon, GitHub,
Reddit, Google Maps.

## Planned by the AI

Anything else. The AI can combine these skills:

| Skill | Does |
|---|---|
| list_folder, find_files | Look inside folders |
| create_folder, move_items, move_matching, rename_item | Change files (undoable) |
| organize_folder | Sort loose files into folders by type (asks first, undoable) |
| delete_items | Send to the Recycle Bin (asks first) |
| open_path, open_app, close_app, running_apps | Files and programs |
| web_search, open_website | Browser |
| set_volume, media_key, power, take_screenshot | System |
| type_text, press_keys | Type or press shortcuts in the active window |
| system_status | CPU, memory, disk, battery, heaviest programs |
| run_powershell | Anything else Windows can do (asks first by default) |

Examples:

- "Create a folder called Old on the desktop and move everything not opened
  in 20 days into it"
- "Move all the PDFs in Downloads to Documents"
- "What is using the most memory?"
- "Rename the file report on my desktop to report-final"

## What always asks first

Deleting, shutting down, restarting, signing out, organising a folder, and
PowerShell (unless you turn that off in Settings).

## "Not opened in N days"

Windows does not reliably record when a file was last opened. Vox uses the
newest of each file's opened, changed and created times.
