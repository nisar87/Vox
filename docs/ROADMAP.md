# Roadmap

The goal, in the owner's words: Vox should behave like a normal person. It
listens properly instead of talking over me or skipping parts of what I said,
and when it cannot do something it learns how, so it never makes the same
mistake every single time.

In practice: understand almost anything, act quickly, need the AI less over
time, and stay out of the way. Target: 95% of everyday requests done
correctly.

Two things follow from that goal and shape every step below:

1. **Listening like a person.** Hear the whole request, do every part of it,
   keep replies short, stop talking the moment I start, ask when unsure
   instead of guessing, and remember what we were just talking about.
2. **Learning from mistakes.** A failure or a correction must change what
   Vox does next time.

Where these stand today:

| | Today (0.3.0) | Still missing |
|---|---|---|
| Hears the whole request | Waits through pauses and keeps listening when a sentence stops mid-thought (0.3.2) | Judging "finished" from the words alone is a rule of thumb; the AI should decide |
| Does every part | The AI returns all steps at once and each is checked | No automatic re-check that nothing was skipped |
| Does not talk over me | Stays silent during dictation and calls | Does not yet stop speaking when I start |
| Asks instead of guessing | Asks before risky actions; the AI is told to ask when unclear | |
| Remembers the conversation | The last six exchanges are given to the AI | Instant commands do not use them ("do that again") |
| Learns what worked | Yes: phrases and patterns, reused without the AI | |
| Learns from failure | A failed or undone plan is forgotten | Does not yet remember why it failed, or what I corrected it to |

Status as of version 0.3.5. Each step lists what "done" means, so progress can
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

### Step 3b. First real-use fixes (0.3.1)
Found on the owner's PC: "Hi Vox" was heard as "Hiles" and "High books", the
AI took 6 to 15 seconds, the voice was robotic, and "open Notepad++ and write
a few lines about education" was not understood.
- Hearing now uses the AI provider by default; the on-PC model is the fallback.
- Minimal thinking and the fastest Gemini model by default.
- Natural AI voice with on-disk caching.
- Wake phrase can be taught to match the owner's voice.
- "Write ..." requests are composed by the AI and typed.

### Step 3c. Second round of real-use fixes (0.3.2)
- Cut-off sentences: longer pause allowance, and Vox keeps listening when a
  sentence stops mid-thought.
- Standby wake: consistent hearing, loose matching, one-press correction.
- Buzz at the end of the AI voice removed.
- Measured on the owner's PC: Gemini answers in about 800 ms.

### Step 3d. Live testing on the owner's PC (0.3.3 to 0.3.5)
Commands were run on the real PC through Vox's own window, and Notepad++ was
looked at to confirm the text arrived.
- Confirmed working: "open Notepad++ and write a few sentences ... in a new
  tab" (about 3 s), YouTube search (instant), greetings, disk-space question,
  create a folder and undo, and a real in-app update from 0.3.2 to 0.3.3.
- Fixed from what was found: writing was skipped or went to the wrong
  window; closing a program that had just been opened; the AI reporting a
  failed step as done; the natural voice failing while standby was on;
  updates leaving installers behind until the C: drive was full.
- Open: the C: drive has about 100 MB free, which blocks updates until space
  is freed. Standby was switched off when first inspected, which is why "Hi
  Vox" got no response; hearing the wake phrase with the real microphone is
  still unconfirmed.

## To verify on the real PC (cannot be tested in the cloud)

These work in automated tests with simulated input. Each needs one real check:

- [x] The Gemini key works (first live AI requests answered, 0.3.0)
- [x] Spoken commands are transcribed correctly (0.3.2, by hotkey)
- [x] The AI model answers quickly (about 800 ms measured, 0.3.1)
- [ ] After 0.3.2: Vox waits for the end of a sentence with pauses in it
- [ ] After 0.3.2: no buzz at the end of spoken replies
- [ ] After 0.3.1: the natural voice plays (Settings, Voice, "Hear it")
- [ ] After teaching, "Hi Vox" wakes standby reliably
- [x] "Open Notepad++ and write a few sentences ..." writes them (seen on screen, 0.3.3)
- [ ] An AI-planned command works, e.g. "move everything on my desktop not
      opened in 20 days into a folder called Old"
- [ ] The same command a second time shows "Learned earlier, no AI needed"
- [x] "Update now" installs a new version and restarts Vox (0.3.2 to 0.3.3)
- [ ] Free space on C:, then update to 0.3.5
- [ ] Hotkey listening with the real microphone
- [ ] "Hi Vox" wakes it reliably; ordinary talk in the room does not
- [ ] Standby shows "paused" during a Teams call and a WhatsApp call
- [ ] Dictation into Notepad and Notepad++, ended with "stop dictation"
- [ ] Windows Security stays quiet about 0.2.1 and later

## Next

### Step 4. Learns from mistakes (0.4)
- **Corrections.** After a wrong result, "no, I meant ..." or "that's wrong,
  do ... instead" replaces what Vox learned, so the same sentence does the
  right thing next time.
- **Teaching.** "When I say 'work mode', open Outlook, Teams and Chrome" is
  stored as a command of my own. "By 'my editor' I mean Notepad++" teaches a
  name.
- **Failure memory.** When something fails, Vox records what was asked and
  why it failed, and gives that to the AI the next time a similar request
  arrives, so it tries a different way instead of repeating the failure.
- **Never the same mistake twice.** A request that failed is retried by the
  AI with the failure in hand; if it then succeeds, the working way is
  learned and the failing way is dropped.
- The Learned screen shows corrections, taught commands and known failures,
  each removable.
- Done when: for ten deliberately failed requests, the second attempt at
  each either succeeds or asks a sensible question, and none repeats the
  first failure unchanged.

### Step 5. Listens like a person (0.5)
- **Stops talking when I start.** Speech is cut the moment my voice is heard.
- **Does not cut me off.** Waits through natural pauses; a longer request
  gets a longer wait.
- **Nothing skipped.** After acting, Vox compares what was done against what
  was asked and finishes or reports anything left over.
- **Follow-ups.** After a command, a short window where I can continue
  without saying "Hi Vox" again: "and close it", "do that again", "no, the
  other one".
- **Short, human replies.** Confirmations of a few words; detail only when
  asked.
- Done when: a five-step spoken request is completed in full, and I can
  interrupt a reply mid-sentence and be heard.

### Step 6. Reliability pass
Driven by what the checks above turn up.
- Fix every failure found on the real PC.
- Wake phrase tuning: measure false wakes and misses over a normal day;
  adjust, or move to a dedicated wake-word model if the general speech model
  is too heavy or too jumpy.
- Speed targets: instant commands under half a second from end of speech;
  AI commands under two seconds.
- Done when: the checklist above is fully ticked.

### Step 7. Measured accuracy
- A fixed list of 100 realistic spoken commands, run before every release.
- A report of how many succeed, published with each release.
- Live AI tests in the cloud build (needs an API key added as a repository
  secret).
- Done when: 95 of 100 pass, three releases in a row.

### Step 8. Browser control
- "Play the first result", "open the second link", "scroll down", "go back".
- Fill in forms and search boxes on the current page.
- Read a page or the selected text aloud; summarise it.
- Done when: "I want to see Pakistan vs Sri Lanka highlights on YouTube"
  starts the video playing, not just the search results.

### Step 9. Smarter dictation and writing
- Spoken punctuation and editing: "new line", "delete that", "select the
  last sentence", "make it formal".
- "Write a reply to this email" using what is on screen.
- Done when: a short email can be written and corrected entirely by voice.

### Step 10. Any program, by looking at the screen
- Click buttons and menus in programs that have no dedicated skill.
- Slower than other routes and the least reliable part; kept behind a
  confirmation at first.
- Done when: ten common tasks in three ordinary programs succeed eight
  times out of ten.

### Step 11. Knows the PC
- "What was I working on yesterday?", "find the contract with the 2024
  pricing", "why is the PC slow?"
- A local index of files and recent activity. Nothing leaves the PC.
- Morning briefing: updates, disk space, yesterday's unfinished work.

### Step 12. From anywhere
- Talk to the PC from a phone browser: send a command, get the result, grab
  a file, see the screen.
- Login and an encrypted connection are prerequisites, since this exposes
  the PC to the internet.

### Step 13. Polish for 1.0
- Code-signed installer, so Windows shows no warning.
- Better voices for replies.
- Urdu alongside English.
- Other devices as skills (the Xiaomi TV box over the network).

## Ideas parked

- Mirroring and controlling the Xiaomi TV box from the PC. Possible over the
  network with Android's debugging feature; streaming apps would show a
  black picture because of copy protection. Folded into Step 13.
- Plain remote desktop over the internet. Chrome Remote Desktop already does
  this well and for free; Step 12 covers the voice-assistant version.

## Working rules

- Anything that deletes, shuts down, reorganises or runs PowerShell asks first.
- Files are moved, never overwritten; changes can be undone.
- What standby hears stays on the PC.
- A release is only published after the cloud build has tested, built,
  installed and self-tested it.
- This file is updated with every release.
