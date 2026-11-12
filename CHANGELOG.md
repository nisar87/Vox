# Changelog

## 0.4.0

**Live conversation.** A new way of listening, modelled on how the better
"Jarvis" assistants work and on Gemini's Live service.

- Your voice is streamed to Gemini for the length of a conversation. The
  model hears you directly, so there is no separate speech-to-text step to
  mishear an accent or a program name.
- The model decides when you have finished, and is set to be patient with
  pauses.
- You can interrupt Vox while it is speaking; it stops and listens.
- No wake word between sentences: after the first request, just keep
  talking. The conversation ends when you say "that's all" or "thanks", after
  25 seconds of quiet, when you press the hotkey again, or when a call starts.
- Replies are spoken in Gemini's live voice as they are generated.
- Risky actions (delete, shut down, PowerShell, reorganise) still need a
  spoken yes, and Vox checks that you answered before it acts.
- "Hi Vox, open Notepad" in one breath: the recording that woke Vox is
  handed to the conversation, so nothing is repeated.
- Dictation now uses the accurate speech engine.
- If the live service cannot be reached, Vox says so and listens the old
  way. Settings, Hearing, Conversation switches between Live and Classic.

Use a headset for live conversation. With loudspeakers Vox can hear its own
voice and interrupt itself.

## 0.3.6

Speaking to Vox, from what was captured on the owner's PC: "Can you open
Notepad++ and open a new sheet there, and then" was all Vox heard; the rest
was said while it was busy and lost.

- **Nothing said is lost any more.** The microphone now stays open for the
  whole request. Whatever you say while Vox is working out the first part is
  kept, joined on, and heard again as one sentence.
- **Vox listens for your answer.** When it asks something ("What would you
  like me to write?"), it listens straight away and treats what you say as
  the answer to that question, completing the original request.
- A record of how each spoken request was captured (length, where it ended,
  what was heard) is kept for diagnosis.

## 0.3.5

Found by running Vox on the owner's PC.

- **Updates left their installer behind.** Each update left about 77 MB in
  the temporary folder, which helped fill the C: drive until "Update now"
  failed with "Something went wrong". Vox now deletes old installers when it
  starts and before each download, checks free space first, and says
  exactly what is wrong when an update cannot proceed.
- **Natural voice failed while standby was on** ("Error opening
  OutputStream"). Speech is now played in the sound card's own format, which
  USB headsets require while the microphone is in use. A single failure no
  longer switches the natural voice off.

## 0.3.4

Found by running commands on the owner's PC.

- "Open the calculator and then close it" closed nothing, because the close
  ran before the program had started. Closing now waits for a program that
  was just opened.
- Vox said "opening and closing Calculator" although the close had failed.
  The AI is now told to report a failed step as failed.
- Text written into programs is composed fresh each time, never replayed
  from memory.
- Standby keeps a short list of what it heard and ignored, to diagnose a
  missed "Hi Vox".

## 0.3.3

- **"Open Notepad++ and write ..." now writes.** Two faults on a real PC: the
  AI sometimes opened the program and skipped the writing, and when it did
  write, Windows had not given Notepad++ the keyboard, so the text went
  nowhere and Vox waited eight seconds. Now there is one skill that opens
  (or switches to) the program, forces its window to the front, optionally
  opens a new tab, and pastes the text. If the AI still skips the writing,
  Vox notices and tells it to finish.
- Requests with several parts get slightly more AI thought, so parts are not
  dropped.
- Long text is pasted, not typed key by key: instant, and unaffected by
  auto-indent. Your clipboard is restored afterwards.
- New: "switch to Notepad++".
- A Standby switch on the Talk screen, and teaching the wake phrase now turns
  standby on.

## 0.3.2

- **No longer cuts you off.** Vox waited only 0.7 seconds of silence before
  acting, so "open Notepad++ and write ..." was taken as finished at "write".
  It now waits 1.4 seconds (adjustable in Settings, Hearing, "Pauses while
  speaking"), and if what it heard stops mid-thought ("... and write") it
  keeps listening for the rest instead of acting on half a sentence.
- **"Hi Vox" in standby.** Three faults: standby used different settings from
  the "Teach" button, so what you taught did not match; a filter threw away
  short phrases; and matching was exact, though the speech model words it
  slightly differently each time. All fixed. When standby hears something
  and ignores it, the window now shows what it heard with a button, "That
  was me saying Hi Vox", which teaches it on the spot.
- **"Hi Vox, open Notepad++ and ..." in one breath** is now re-heard by the
  accurate engine, not the small on-PC model.
- **Buzz at the end of the AI voice.** Speech now fades out and the audio
  device is closed properly.

## 0.3.1

Fixes from the first real use: Vox misheard speech, took up to 15 seconds to
answer, and its voice was poor.

- **Understands speech far better.** Hearing is now "Automatic": your AI
  provider transcribes what you say, which copes with accents and names such
  as Notepad++. The small on-PC model that heard "Hi Vox" as "Hiles" is now
  only the offline fallback. Existing installs are switched over.
- **Much faster AI answers.** The Gemini model was spending 6 to 14 seconds
  "thinking" about simple commands. Vox now asks for minimal thinking and
  defaults to the fastest model (Gemini 3.5 Flash-Lite).
- **Natural voice.** Replies use your provider's AI voice instead of the
  robotic Windows one. Common sentences are kept on disk so they play
  instantly. If the AI voice fails, Vox says why and falls back to Windows.
  Choose the voice in Settings, Voice, and press "Hear it".
- **Teach Vox your "Hi Vox".** Standby listens on the PC only, so it can
  still mishear the wake phrase. Settings, Hearing, "Teach Vox my Hi Vox"
  records you saying it and learns what your voice sounds like to it.
- **"Open Notepad++ and write a few lines about education"** now goes to the
  AI, which writes the text and types it. "Type hello world" still types
  exactly what you said. "Notepad plus plus" is recognised.
- "Hello" and "thank you" are answered instantly, without the AI.

## 0.3.0

- **Standby: say "Hi Vox".** Switch it on in Settings, Hearing (or from the
  tray icon) and Vox listens in the background with its window closed. Say
  "Hi Vox" and it answers "Yes <your name>, I'm listening", or say it in one
  go: "Hi Vox, open Notepad". What it hears stays on the PC and is discarded
  unless it starts with "Hi Vox".
- **Quiet during calls.** Standby pauses while another program is using the
  microphone (Teams, WhatsApp, Zoom, a browser call) and resumes afterwards.
- **Your name.** Settings, Voice, "Your name". Filled in from your Windows
  account to start with.
- **Dictation.** "Open Notepad and keep writing what I say" opens the program
  and types everything you say, silently, until you say "stop dictation".
  "Open Notepad and write hello world" types one line.
- **More natural phrasing.** "I want to see Pakistan vs Sri Lanka match
  highlights on YouTube", "show me ... on YouTube", "I'd like to watch ...".
- **Yes/no by voice.** When Vox asks a question it now listens for your
  answer straight away.
- **Fixed: "Unable to open file 'model.bin'".** The speech model is now kept
  in Vox's own folder and is downloaded again automatically if it is damaged
  or incomplete.

## 0.2.2

- **API key could not be saved.** The key box in Settings shared an internal
  name with another element, so a pasted key was never stored and Vox kept
  saying "Enter the API key first". Fixed, with a test that prevents a repeat.
- Pasting a key now saves it at once, and "Load models" and "Test speed"
  save whatever is in the box before running.
- The model list shows only Gemini models that can plan commands.

## 0.2.1

Fixes the two problems found installing 0.2.0.

- **Antivirus quarantine.** Microsoft Defender quarantined 0.2.0's `Vox.exe`
  as `Trojan:Win32/Bearfoos.A!ml`, a machine-learning false positive common
  with self-extracting Python launchers. Vox no longer uses one. `Vox.exe` is
  now the official Python runtime, digitally signed by the Python Software
  Foundation, running Vox's plain source code.
- **"Internal Server Error" in the window.** Caused by the same quarantine:
  Vox could no longer read parts of itself from the blocked file. With no
  packed file this cannot recur, and the window now explains the problem if
  Windows ever blocks a Vox file.
- If another program is using Vox's port, Vox picks a free one instead of
  showing that program's page.
- Self-test command is now `Vox.exe -m vox --self-test report.json`.

## 0.2.0

First installable release.

- **Installer.** `VoxSetup-0.2.0.exe` installs Vox for the current user, with
  optional desktop shortcut and start-with-Windows. No Python needed.
- **Updates.** Vox checks GitHub for a newer release when it starts. Settings,
  Updates, "Update now" downloads the installer, verifies its checksum,
  installs it and restarts Vox.
- **Self-learning.** When the AI plans a command, Vox remembers the plan. The
  same sentence next time runs with no AI request, and after two similar
  examples Vox handles new variations too. The Learned screen lists
  everything remembered and lets you forget any of it.
- **Self-test.** `--self-test report.json` checks every part of the
  installed copy.
- Second launches reuse the running copy instead of starting another.

## 0.1.0

- Instant router for everyday commands, AI planning with Gemini or OpenAI,
  file, program, web and system skills, confirmation and undo, voice input
  and spoken replies, settings window.
