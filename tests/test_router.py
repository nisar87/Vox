import pytest

from vox import router

SEARCHES = [
    ("Open Google Chrome and search for best laptops 2026.", "google", "best laptops 2026", "chrome"),
    ("open youtube in chrome and search for lofi beats in youtube", "youtube", "lofi beats", "chrome"),
    ("Open YouTube and search for python tutorial", "youtube", "python tutorial", None),
    ("open youtube, search cooking biryani", "youtube", "cooking biryani", None),
    ("search for cat videos on youtube", "youtube", "cat videos", None),
    ("play despacito on youtube", "youtube", "despacito", None),
    ("search youtube for mr beast", "youtube", "mr beast", None),
    ("Hey Vox, can you please google weather in lahore", "google", "weather in lahore", None),
    ("look up fastapi websockets", "google", "fastapi websockets", None),
    ("search for flights to dubai please", "google", "flights to dubai", None),
    ("search wikipedia for alan turing", "wikipedia", "alan turing", None),
    ("open edge and search for cricket score", "google", "cricket score", "edge"),
    ("find react hooks on github", "github", "react hooks", None),
]


@pytest.mark.parametrize("said,site,query,browser", SEARCHES)
def test_searches(vox, said, site, query, browser):
    calls = router.match(said)
    assert calls and calls[0][0] == "web_search", said
    args = calls[0][1]
    assert (args["site"], args["query"], args.get("browser")) == (site, query, browser)


SIMPLE = [
    ("open youtube", ("open_website", {"site": "youtube"})),
    ("go to gmail in chrome", ("open_website", {"site": "gmail", "browser": "chrome"})),
    ("open bbc.com", ("open_website", {"site": "bbc.com"})),
    ("open notepad", ("open_app", {"name": "notepad"})),
    ("Launch Chrome.", ("open_app", {"name": "google chrome"})),
    ("open the spotify app", ("open_app", {"name": "spotify"})),
    ("open my downloads folder", ("open_path", {"path": "downloads"})),
    ("close notepad", ("close_app", {"name": "notepad"})),
    ("volume up", ("set_volume", {"change": 10})),
    ("turn the volume down", ("set_volume", {"change": -10})),
    ("set volume to 40 percent", ("set_volume", {"level": 40})),
    ("mute", ("set_volume", {"mute": True})),
    ("pause the music", ("media_key", {"action": "play_pause"})),
    ("next song", ("media_key", {"action": "next"})),
    ("lock my pc", ("power", {"action": "lock"})),
    ("shut down the computer", ("power", {"action": "shutdown"})),
    ("take a screenshot", ("take_screenshot", {})),
    ("undo that", ("undo_last", {})),
]


@pytest.mark.parametrize("said,expected", SIMPLE)
def test_simple_commands(vox, said, expected):
    assert router.match(said) == [expected], said


# These must NOT be handled instantly: they need the AI to plan.
FOR_THE_AI = [
    "organise my desktop",
    "create a directory on desktop and move all my desktop items which were not opened from 20 days",
    "search for files named invoice on my desktop",
    "find the report I downloaded last week",
    "open visual studio",  # two installed programs match: ambiguous
    "open chrome and notepad",
    "open the budget spreadsheet in excel",
    "close everything except chrome",
    "volume up and open notepad",
    "how much disk space do I have",
    "open photoshop",  # not installed
]


@pytest.mark.parametrize("said", FOR_THE_AI)
def test_left_for_the_ai(vox, said):
    assert router.match(said) is None, said


def test_yes_no():
    assert router.yes_no("Yes, go ahead.") is True
    assert router.yes_no("yes") is True
    assert router.yes_no("Go ahead") is True
    assert router.yes_no("No, cancel that") is False
    assert router.yes_no("open notepad") is None


def test_time_answer():
    assert router.answer("What time is it?").startswith("It's ")
    assert router.answer("what is the weather") is None
