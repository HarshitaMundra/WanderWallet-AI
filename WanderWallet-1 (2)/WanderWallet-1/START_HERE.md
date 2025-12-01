# 🎯 WanderWallet - Kaise Shuru Karein? (START HERE!)

---

## 🚀 VS Code Pe Chalana Hai? (Hindi Guide)

**Sabse Easy Way:**

### Windows Users:
1. Double-click karo: **`setup_windows.bat`**
2. Script automatically sab setup kar dega
3. `.env` file mein apni API keys add karo
4. Terminal mein run karo: `python app.py`

### Mac/Linux Users:
1. Terminal mein run karo: `./setup_mac_linux.sh`
2. `.env` file mein apni API keys add karo
3. Terminal mein run karo: `python app.py`

### Manual Setup (Step-by-step):
📖 **Complete Hindi Guide:** [VS_CODE_SETUP_HINDI.md](VS_CODE_SETUP_HINDI.md)

---

## 📚 All Documentation Files:

| File | Description | For Whom? |
|------|-------------|-----------|
| **VS_CODE_SETUP_HINDI.md** | Quick 5-minute setup (Hindi) | VS Code users (Hindi) |
| **VS_CODE_QUICK_START.md** | Detailed guide with troubleshooting (Hindi) | VS Code users (detailed) |
| **LOCAL_SETUP.md** | Complete setup guide (English) | English speakers |
| **README.md** | Project overview & features | Everyone |

---

## ⚡ Quick Setup Summary:

```bash
# 1. Virtual Environment Banao
python -m venv venv             # Windows
python3 -m venv venv            # Mac/Linux

# 2. Activate Karo
venv\Scripts\activate           # Windows
source venv/bin/activate        # Mac/Linux

# 3. Packages Install Karo
pip install -r requirements.txt

# 4. .env File Banao
copy .env.example .env          # Windows
cp .env.example .env            # Mac/Linux

# 5. API Keys Add Karo (.env file mein)
# - GEMINI_API_KEY
# - UNSPLASH_ACCESS_KEY
# - SESSION_SECRET

# 6. App Chalao
python app.py

# 7. Browser Mein Kholo
# http://localhost:5000
```

---

## 🔑 API Keys Kaha Se Milenge?

### GEMINI_API_KEY (Required):
- 🔗 https://aistudio.google.com/app/apikey
- Click: "Create API Key"
- Copy karke `.env` mein paste karo

### UNSPLASH_ACCESS_KEY (Optional - for images):
- 🔗 https://unsplash.com/oauth/applications
- Create new application
- Copy "Access Key"

### SESSION_SECRET (Required):
Terminal mein run karo:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Output copy karke `.env` mein paste karo

---

## ✅ Features After Setup:

- ✨ **AI-Powered Budget Insights** (Gemini AI)
- 🗺️ **Smart Travel Planning**
- 🏨 **Hotel & Tourist Recommendations**
- 📸 **Beautiful Destination Images** (Unsplash)
- 📱 **Mobile-Friendly Design**
- 🔐 **Secure User Authentication**
- 📊 **Budget Tracking (50/30/20 Rule)**
- 📝 **Quick Notes Feature**

---

## 🆘 Help Needed?

### Quick Fixes:
1. **"GEMINI_API_KEY not found"** → Check `.env` file banaya hai?
2. **"Port 5000 in use"** → `app.py` mein port 5001 use karo
3. **"Module not found"** → `pip install -r requirements.txt` run karo
4. **Database errors** → `database.db` delete karo, phir app run karo

### Detailed Help:
- 📖 [VS_CODE_SETUP_HINDI.md](VS_CODE_SETUP_HINDI.md) - Complete Hindi guide
- 📖 [VS_CODE_QUICK_START.md](VS_CODE_QUICK_START.md) - Troubleshooting
- 📖 [LOCAL_SETUP.md](LOCAL_SETUP.md) - English guide

---

## 📂 Important Files:

```
wanderwallet/
├── START_HERE.md           ← YEH FILE (setup guide)
├── setup_windows.bat       ← Windows auto-setup
├── setup_mac_linux.sh      ← Mac/Linux auto-setup
├── app.py                  ← Main application
├── .env                    ← API KEYS YAHA DAALO!
├── .env.example            ← Template
├── requirements.txt        ← Dependencies
├── database.db             ← Auto-created
├── templates/              ← HTML files
├── static/css/             ← Styles
└── utils/                  ← Backend logic
```

---

## 🎊 Ready to Start?

1. **Setup Script** chalao (Windows: `setup_windows.bat`, Mac/Linux: `./setup_mac_linux.sh`)
2. **`.env` file** mein API keys add karo
3. **`python app.py`** run karo
4. **`http://localhost:5000`** browser mein kholo
5. **Mobile pe bhi test karo!** 📱

---

## 🌟 Happy Coding!

Questions? Check:
- VS_CODE_SETUP_HINDI.md
- VS_CODE_QUICK_START.md
- LOCAL_SETUP.md

**Your app is ready to run! 🚀**
