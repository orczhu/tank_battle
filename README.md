# Tank Battle 🛡️

A two-player tank game inspired by the classic *Battle City* (Namco, 1985).
One computer runs the game; two players join from any computer on the same WiFi using a web browser.

## Start the game

On the computer that runs the game (needs Python 3):

```
pip3 install aiohttp      # first time only
python3 server.py
```

It prints an address, for example:

```
 On each computer, open:  http://10.0.0.212:8080
```

Keep this window open while playing.

## Join the game

On each player's computer (Windows, Mac, or Chromebook):

1. Connect to the **same WiFi** as the game computer.
2. Open **Chrome** or **Edge** and go to the address printed above.
3. The first player to join is the **yellow** tank (Player 1); the second is the **green** tank (Player 2).
4. Press **Enter** to start.

## Controls

| Action | Keys |
|---|---|
| Move | Arrow keys or W A S D |
| Fire | Space or J |
| Start / play again | Enter |
| Sound on/off | M |

## How to win

- **Protect the eagle 🦅** at the bottom of the map. If an enemy shoots it, the game is over.
- Destroy all **20 enemy tanks** to clear the stage. The gray squares on the right show how many are left.
- Each player starts with **3 lives** (♥ on the right).

## The map

| Tile | What it does |
|---|---|
| 🧱 Brick (red-brown) | Blocks tanks. Shoot it to break it. |
| ⬜ Steel (gray) | Blocks tanks and bullets. Only breaks with 3 stars. |
| 🟦 Water | Tanks can't cross; bullets fly over it. |
| 🌳 Trees | Tanks can hide underneath. |

## Enemy tanks

| Color | Type |
|---|---|
| Gray | Basic: slow |
| Blue | Fast: moves quickly |
| Orange | Power: shoots fast bullets |
| Purple → pink → gold → gray | Armor: takes 4 hits, changes color each hit |
| **Flashing red** | Hit it to make a power-up appear! |

## Power-ups

| Icon | Effect |
|---|---|
| ⭐ Star | Upgrade your tank: faster bullets → two bullets → breaks steel |
| 💣 Grenade | Blows up every enemy on screen |
| 🛡️ Helmet | Shield: nothing can hurt you for 10 seconds |
| 🏰 Shovel | Turns the eagle's wall to steel for 20 seconds |
| ⏰ Timer | Freezes all enemies for 10 seconds |
| ❤️ Tank | One extra life |

## Friendly rules

- Your own bullets can't hurt the eagle, so you can't lose by accident.
- Shooting your teammate just freezes them for 2 seconds.
- If you run out of lives, you come back with 1 life on the next stage.
- If your teammate joins late, they jump right into the game.

## Trouble connecting?

- The address must start with `http://` (not `https://`) and end with `:8080`.
- On a Mac game computer: **System Settings → Network → Firewall**, allow incoming connections for Python.
- Guest WiFi networks often block computers from seeing each other; use the main WiFi.
- The address can change after the router restarts; use the one `server.py` prints.
