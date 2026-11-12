# Roadmap

The goal: talk to the PC like a capable assistant. It should understand
almost anything, act quickly, need the AI less over time, and stay out of the
way. Target: 95% of everyday requests done correctly.

Status as of version 0.3.0. Each step lists what "done" means, so progress can
be checked rather than assumed.

## Done

### Step 1. Core assistant (0.1)
- Instant commands with no AI request: programs, sites, searches, volume,
  media, lock, screenshot, undo.
- AI planning with Gemini or OpenAI for everything else, in one request.
- File skills with confirmation and undo.
- Settings window, timing bar for every command.

### Step 2. Installer, updates, learning (0.2)
- Windows installer; no Python needed.
- In-app updates from GitHub Releases with checksum verification.
- Self-learning: AI plans are remembered and reused; patterns generalise
  after two examples.
- Every release is tested, built, installed and self-tested on GitHub first.
- 0.2.1: rebuilt on the signed Python runtime after antivirus quarantined the
  first build. 0.2.2: API key saving fixed.

### Step 3. Hands-free (0.3)
- Standby with the wake phrase "Hi Vox" and a personal greeting.
- Pauses while another program uses the microphone (calls).
- Dictation into any program.
- Natural phrasing for watching and searching.
- Speech model stored safely and repaired automatically.

## To verify on the real PC (cannot be tested in the cloud)

These work in automated tests with simulated input. Each needs one real check:

- [ ] "Test speed" succeeds with the Gemini key (first live AI request)
- [ ] An AI-planned command works, e.g. "move everything on my desktop not
      opened in 20 days into a folder called Old"
- [ ] The same command a second time shows "Learned earlier, no AI needed"
- [ ] "Update now" installs a new version and restarts Vox
- [ ] Hotkey listening with the real microphone
- [ ] "Hi Vox" wakes it reliably; ordinary talk in the room does not
- [ ] Standby shows "paused" during a Teams call and a WhatsApp call
- [ ] Dictation into Notepad and Notepad++, ended with "stop dictation"
- [ ] Windows Security stays quiet about 0.2.1 and later

## Next

### Step 4. Reliability pass (0.3.x)
Driven by what the checks above turn up.
- Fix every failure found on the real PC.
- Wake phrase tuning: measure false wakes and misses over a normal day;
  adjust, or move to a dedicated wake-word model if the general speech model
  is too heavy or too jumpy.
- Speed targets: instant commands under half a second from end of speech;
  AI commands under two seconds.
- Done when: the checklist above is fully ticked.

### Step 5. Measured accuracy (0.4)
- A fixed list of 100 realistic spoken commands, run before every release.
- A report of how many succeed, published with each release.
- Live AI tests in the cloud build (needs an API key added as a repository
  secret).
- Done when: 95 of 100 pass, three releases in a row.

### Step 6. Browser control (0.5)
- "Play the first result", "open the second link", "scroll down", "go back".
- Fill in forms and search boxes on the current page.
- Read a page or the selected text aloud; summarise it.
- Done when: "I want to see Pakistan vs Sri Lanka highlights on YouTube"
  starts the video playing, not just the search results.

### Step 7. Smarter dictation and writing (0.6)
- Spoken punctuation and editing: "new line", "delete that", "select the
  last sentence", "make it formal".
- "Write a reply to this email" using what is on screen.
- Done when: a short email can be written and corrected entirely by voice.

### Step 8. Any program, by looking at the screen (0.7)
- Click buttons and menus in programs that have no dedicated skill.
- Slower than other routes and the least reliable part; kept behind a
  confirmation at first.
- Done when: ten common tasks in three ordinary programs succeed eight
  times out of ten.

### Step 9. Knows the PC (0.8)
- "What was I working on yesterday?", "find the contract with the 2024
  pricing", "why is the PC slow?"
- A local index of files and recent activity. Nothing leaves the PC.
- Morning briefing: updates, disk space, yesterday's unfinished work.

### Step 10. From anywhere (0.9)
- Talk to the PC from a phone browser: send a command, get the result, grab
  a file, see the screen.
- Login and an encrypted connection are prerequisites, since this exposes
  the PC to the internet.

### Step 11. Polish for 1.0
- Code-signed installer, so Windows shows no warning.
- Better voices for replies.
- Urdu alongside English.
- Other devices as skills (the Xiaomi TV box over the network).

## Ideas parked

- Mirroring and controlling the Xiaomi TV box from the PC. Possible over the
  network with Android's debugging feature; streaming apps would show a
  black picture because of copy protection. Folded into Step 11.
- Plain remote desktop over the internet. Chrome Remote Desktop already does
  this well and for free; Step 10 covers the voice-assistant version.

## Working rules

- Anything that deletes, shuts down, reorganises or runs PowerShell asks first.
- Files are moved, never overwritten; changes can be undone.
- What standby hears stays on the PC.
- A release is only published after the cloud build has tested, built,
  installed and self-tested it.
- This file is updated with every release.
