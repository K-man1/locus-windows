# Locus
Locus is a Windows app that keeps you focused on whatever you are working on. You start by typing what you are working on, like "Math HW" or selecting something from a calender you connected. Then you visit a website/app. If the AI thinks that you are on task (like visiting math.com or something idk while in Math HW session), nothing happens. However if you visit something like fungames.com when in your focus session, it asks you why you need to visit the website. You can explain why, and if the AI finds it plausible, you're good! Otherwise, it'll block it and prevent you from visit the website.

I made it because I was using other blockers, and I thought that this was a really good idea with a pretty simple implementation!

One thing: its not meant to be perfect. The idea is to make you think twice before visit that website and by forcing you to write out your reason it makes you wonder yourself "why am i trying to watch youtube?" and it also makes you pause and relax for a second.

## Install
```
git clone https://github.com/k-man1/locus-windows.git
cd locus-windows

python --version                       # must be 3.10+
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt

mkdir "$env:APPDATA\Locus" -Force
Copy-Item config.example.json "$env:APPDATA\Locus\config.json"

# browser must run with the debug port for website blocking
Start-Process "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe" `
  "--remote-debugging-port=9222 --remote-allow-origins=*"

.\.venv\Scripts\python.exe locus_app.py
```
- Python 3.10+
- pyinstaller to install the .exe
