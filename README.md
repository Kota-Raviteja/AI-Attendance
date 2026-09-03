# FaceID — Face Recognition Attendance System

A Flask + OpenCV (Haar cascade + LBPH) attendance system with a live camera
check-in station, role-based admin/user dashboards, and a fully
customizable theme and shift configuration.

---

## 1. What's new in this version

- **Real accounts with roles** — no more single shared "admin" password.
  Every person who logs in has a username, a hashed password, and a role
  (`admin` or `user`).
- **Admins can create new users. Regular users cannot.** `/register`,
  `/manage`, `/settings`, and their APIs are now protected server-side
  (previously `/register` had no protection at all — anyone with the URL
  could register a new face).
- **Two different dashboards:**
  - **Admin dashboard** — today's check-ins, total registered users, a
    7-day check-in trend chart, and the full recent-activity feed across
    everyone.
  - **User dashboard** — only their own check-in history and shift info.
- **Fully customizable Settings page (admin only):** brand name, accent
  color (presets or custom gradient), shift length in hours, recognition
  strictness, the Database vault passcode, and default sound behavior —
  all editable at runtime, no code changes.
- **Redesigned, responsive UI** — mobile nav, avatar badges, a live capture
  progress grid on registration, searchable user database, credential
  reveal box when an admin creates a login, toast notifications, empty
  states throughout.
- **Fixed a real security hole:** the Database "Vault" passcode used to be
  checked entirely in client-side JavaScript (`if (pass === "vault")`),
  which anyone could bypass by reading the page source. It's now verified
  server-side.
- **New capabilities:** delete a registered user (removes their face data,
  retrains the model, and removes any linked login), generate a login for
  an existing face-only profile, CSV export of attendance, and a
  self-service password-change page.
- **OpenCV stays pinned at 4.10** — `recognition_logic.py`'s detection/
  training code is unchanged; `requirements.txt` pins
  `opencv-contrib-python==4.10.0.84` on purpose. See note in that file.

---

## 2. Project structure

```
Project/
├── app.py                 # Flask routes, auth wiring, camera streaming
├── auth.py                 # Accounts, password hashing, role decorators
├── settings.py              # Site-wide customizable config (theme, shift, etc.)
├── recognition_logic.py     # Face detection + LBPH training/recognition
├── requirements.txt
├── users.json               # name -> shift start time (face profiles)
├── accounts.json            # login accounts (created on first run)
├── config.json              # customizable settings (created on first run)
├── attendance.csv           # attendance log
├── trainer.yml               # trained LBPH model
├── faces/                    # per-user folders of captured face images
├── static/
│   ├── css/style.css
│   └── sounds/
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard_admin.html
    ├── dashboard_user.html
    ├── register.html         # admin only
    ├── manage.html            # admin only — user database / vault
    ├── settings.html           # admin only
    ├── profile.html
    └── attendance.html         # live check-in camera page
```

`fix_templates.py` and `migrate_faces.py` are one-off dev utilities from
earlier in the project; they're harmless to keep and not part of the app's
runtime.

---

## 3. Setup

```bash
cd Project
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

The pinned `opencv-contrib-python==4.10.0.84` is intentional — that's the
version your face recognition was built and tested against. If `pip`
can't find that exact build for your platform, install the closest 4.10.x
patch release instead of jumping to a newer major version.

### Run it

```bash
python app.py
```

Visit `http://localhost:5000`. On first run, `accounts.json` and
`config.json` are created automatically with sensible defaults.

### Default admin login

```
Username: admin
Password: admin
```

**Change this password immediately** from the Profile page after your
first login — the app ships with this default so it boots without any
manual setup, but it's not meant to stay in place.

---

## 4. Roles, in practice

**Admin**
- Sees the system-wide dashboard, trend chart, and full activity feed.
- Registers new users (face capture + shift time), optionally creating a
  login for them in the same flow — a generated password is shown once.
- Manages the user database: search, view samples, delete a user, or
  generate a login for someone who was registered before login accounts
  existed.
- Edits Settings: branding, accent color, shift length, recognition
  strictness, vault passcode, default sound preference.

**User**
- Sees only their own check-in history and current shift start time.
- Can check in via the Live Check-in camera page (face recognition still
  runs the same way for everyone — the role only affects what they can
  navigate to and see).
- Can change their own password from Profile.
- Has no access to `/register`, `/manage`, `/settings`, or their APIs —
  enforced server-side, not just hidden in the nav.

### Linking an existing face profile to a login

Your original `users.json` already has 9 people registered (Ravi, Satvik,
Tester, etc.) but no login accounts exist for them yet — the previous
version of the app didn't have individual logins at all. To let one of
them log in and see their own dashboard, go to **Database → [their card] →
Create Login**, pick a username, and share the generated password with
them.

> Note: the `faces/` folder in this upload was empty even though
> `users.json` lists 9 people and `trainer.yml` is a trained model file.
> If check-ins stop recognizing existing faces, you'll need to
> re-register those people from the Register page — the images
> themselves weren't included in what was uploaded.

---

## 5. Customizing

Everything under **Settings** is meant to be tweaked without touching
code:

- **Brand name** — shown in the nav and browser tab.
- **Accent color** — five presets or a custom start/end gradient color.
- **Shift length** — hours per shift, used to compute check-in periods.
- **Recognition strictness** — the LBPH distance threshold; lower is
  stricter (fewer false positives, more rejected valid faces), higher is
  more lenient.
- **Vault passcode** — required to view the Database page.
- **Default sound** — whether the Live Check-in page plays a chime/buzz
  by default (each visitor can still toggle it per-session).

All of this is stored in `config.json` and re-read on save — no restart
needed.

---

## 6. Notes on the recognition pipeline

Unchanged from your original implementation, on purpose:
- Haar cascade for face **detection**.
- LBPH (`cv2.face.LBPHFaceRecognizer_create`) for face **recognition**,
  trained on histogram-equalized, resized (200×200) face crops.
- Model retrains automatically whenever a user is registered or deleted.

If you ever do want to move OpenCV versions, re-test registration →
training → recognition end to end first, since LBPH internals have
shifted across some opencv-contrib releases.
