"""MotoScript AI v1.0.0 - Generador de guiones virales de humor sobre motos con Gemini."""
import json
import os
import queue
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests

APP_NAME = "MotoScript AI"
VERSION = "1.0.0"
ORANGE = "#FF5A00"
ORANGE_DARK = "#C2410C"
DARK = "#161616"
SIDEBAR = "#1c1c1c"

DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MotoScriptAI")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
TOKEN_FILE = os.path.join(DATA_DIR, "google_token.json")
CLIENT_SECRET_FILE = os.path.join(DATA_DIR, "client_secret.json")

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
SCOPES = [
    "https://www.googleapis.com/auth/generative-language.retriever",
    "https://www.googleapis.com/auth/cloud-platform",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]
MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
TONES = ["Humor absurdo", "Sarcástico", "Meme viral", "Humor negro suave", "Drama exagerado"]
DURATIONS = ["Reel 15s", "Reel 30s", "Reel 60s"]

EXAMPLE = '''"TEXTO EN PANTALLA": YO JODIENDO A LA IA A LAS 2AM
"VOZ OFF MIENTRAS SE MODIFICA LA IMAGEN": A ver ChatGPT, colócame una moto más grande
"LO QUE SE MUESTRA EN PANTALLA": El sujeto sentado en una moto gigante, modo humor
"VOZ OFF MIENTRAS SE MODIFICA LA IMAGEN": NOOO, cuando te digo una moto más grande me refiero a mayor cilindraje, no al tamaño físico
"LO QUE SE MUESTRA EN PANTALLA": Una foto de la moto pero con un motor gigante asomándose
"VOZ OFF MIENTRAS SE MODIFICA LA IMAGEN": Más o menos, pero quiero algo de mayor cilindraje
"LO QUE SE MUESTRA EN PANTALLA": Pone una moto de mayor CC pero al lado de él, y él sigue en su moto normal'''


# ----------------------------------------------------------------- utilidades
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------- Google OAuth
def google_login():
    """Abre el navegador, inicia sesión y guarda el token. Devuelve el correo."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not os.path.exists(CLIENT_SECRET_FILE):
        raise RuntimeError("Primero selecciona tu archivo client_secret.json (ver README).")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return google_email(creds.token)


def google_email(token):
    try:
        r = requests.get("https://www.googleapis.com/oauth2/v3/userinfo",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return r.json().get("email", "cuenta de Google")
    except Exception:
        return "cuenta de Google"


def google_token():
    """Devuelve un access token válido (lo refresca si hace falta) o None."""
    if not os.path.exists(TOKEN_FILE):
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            return None
    return creds.token


# ----------------------------------------------------------------- Gemini
def auth_headers(cfg):
    h = {"Content-Type": "application/json"}
    if cfg.get("auth") == "google" and os.path.exists(TOKEN_FILE):
        tok = google_token()
        if not tok:
            raise RuntimeError("Sesión de Google caducada. Inicia sesión de nuevo.")
        h["Authorization"] = f"Bearer {tok}"
        if cfg.get("project"):
            h["x-goog-user-project"] = cfg["project"]
    elif cfg.get("api_key"):
        h["x-goog-api-key"] = cfg["api_key"]
    else:
        raise RuntimeError("No hay conexión. Ve a Configuración y conecta tu cuenta o API Key.")
    return h


def validate_api_key(key):
    r = requests.get(f"{API_BASE}/models", headers={"x-goog-api-key": key}, timeout=20)
    return r.status_code == 200


def build_prompt(tone, duration, tiktok):
    seconds = "".join(c for c in duration if c.isdigit()) or "30"
    scenes = {"15": "3 a 4", "30": "5 a 7", "60": "8 a 12"}.get(seconds, "5 a 7")
    return f"""Eres guionista de videos virales de humor sobre MOTOCICLISTAS para Reels/TikTok.
Escribe UN guion nuevo y ORIGINAL en español, con exactamente la misma estructura de este ejemplo viral:

{EXAMPLE}

Reglas:
- Tema: un motociclista que le pide a una IA que edite una foto encima de su moto, y la IA entiende todo mal de forma graciosa. Tienes libertad total para inventar la petición (más cilindraje, más cromo, escape, luces, pilotos, casco, etc.).
- Tono: {tone}. Duración objetivo: {duration} ({scenes} escenas).
- {"Estilo viral TikTok: gancho potente en el primer segundo, ritmo rápido, remate inesperado al final." if tiktok else "Ritmo normal, remate al final."}
- La primera línea es "TEXTO EN PANTALLA" con un título gancho en MAYÚSCULAS.
- Después alterna "VOZ OFF MIENTRAS SE MODIFICA LA IMAGEN" (lo que dice el motociclista) y "LO QUE SE MUESTRA EN PANTALLA" (lo que la IA hace en la imagen).
- Usa EXACTAMENTE estas etiquetas, cada una en su propia línea seguida de dos puntos, y el texto debajo:
TEXTO EN PANTALLA:
VOZ OFF MIENTRAS SE MODIFICA LA IMAGEN:
LO QUE SE MUESTRA EN PANTALLA:
- No añadas introducción, comentarios, markdown ni asteriscos. Solo el guion."""


def generate_script(cfg, tone, duration, tiktok):
    url = f"{API_BASE}/models/{cfg.get('model', MODELS[0])}:generateContent"
    body = {
        "contents": [{"parts": [{"text": build_prompt(tone, duration, tiktok)}]}],
        "generationConfig": {"temperature": 1.1, "maxOutputTokens": 2048},
    }
    r = requests.post(url, headers=auth_headers(cfg), json=body, timeout=90)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = r.text[:300]
        raise RuntimeError(f"Error {r.status_code}: {msg}")
    data = r.json()
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except Exception:
        raise RuntimeError("Gemini no devolvió texto (posible bloqueo de seguridad). Intenta de nuevo.")
    tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
    return text.strip().replace("**", ""), tokens


# ----------------------------------------------------------------- Interfaz
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(f"{APP_NAME}")
        self.geometry("1100x720")
        self.minsize(960, 640)
        self.configure(fg_color="#eef0f4")

        self.cfg = load_json(CONFIG_FILE, {"auth": "none", "api_key": "", "email": "", "model": MODELS[0], "project": ""})
        self.history = load_json(HISTORY_FILE, [])
        self.q = queue.Queue()
        self.pages = {}
        self.nav = {}
        self.last_script = ""

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.build_topbar()
        self.build_sidebar()
        self.build_statusbar()
        self.build_generator()
        self.build_settings()
        self.build_history()
        self.build_about()
        self.show("Generador")
        self.refresh_connection()
        self.after(100, self.poll)

    # --- helpers
    def poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def run_bg(self, work, done):
        def target():
            try:
                res = work()
                self.q.put(lambda: done(res, None))
            except Exception as e:
                err = e
                self.q.put(lambda: done(None, err))
        threading.Thread(target=target, daemon=True).start()

    def connected(self):
        return (self.cfg.get("auth") == "google" and os.path.exists(TOKEN_FILE)) or \
               (self.cfg.get("auth") == "apikey" and bool(self.cfg.get("api_key")))

    # --- barras
    def build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=DARK, corner_radius=0, height=64)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(bar, text="🏍  MotoScript ", font=("Segoe UI", 22, "bold"), text_color="white").pack(side="left", padx=(20, 0), pady=14)
        ctk.CTkLabel(bar, text="AI", font=("Segoe UI", 22, "bold"), text_color=ORANGE).pack(side="left")
        self.conn_label = ctk.CTkLabel(bar, text="", font=("Segoe UI", 13), corner_radius=16, padx=14, pady=4)
        self.conn_label.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkButton(bar, text="⚙", width=40, fg_color="transparent", hover_color="#333",
                      font=("Segoe UI", 20), command=lambda: self.show("Configuración")).pack(side="right", padx=15)

    def build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=240)
        sb.grid(row=1, column=0, sticky="ns")
        sb.grid_propagate(False)
        items = [("Configuración", "⚙"), ("Generador", "🎬"), ("Historial", "🕘"), ("Acerca de", "ⓘ")]
        for name, icon in items:
            b = ctk.CTkButton(sb, text=f"  {icon}   {name}", anchor="w", height=46, corner_radius=8,
                              font=("Segoe UI", 15), fg_color="transparent", hover_color="#2a2a2a",
                              command=lambda n=name: self.show(n))
            b.pack(fill="x", padx=10, pady=(14 if name == "Configuración" else 4, 0))
            self.nav[name] = b
        self.user_label = ctk.CTkLabel(sb, text="👤  Sin cuenta conectada", text_color="#ddd", anchor="w", font=("Segoe UI", 13))
        self.user_label.pack(side="bottom", fill="x", padx=16, pady=20)

    def build_statusbar(self):
        sb = ctk.CTkFrame(self, fg_color="#e4e6eb", corner_radius=0, height=32)
        sb.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status = ctk.CTkLabel(sb, text="● Listo", text_color="#16a34a", font=("Segoe UI", 12))
        self.status.pack(side="left", padx=16)
        self.model_label = ctk.CTkLabel(sb, text="", text_color="#555", font=("Segoe UI", 12))
        self.model_label.pack(side="right", padx=16)

    def set_status(self, text, color="#16a34a"):
        self.status.configure(text=f"● {text}", text_color=color)

    def show(self, name):
        for n, f in self.pages.items():
            f.grid_forget()
            self.nav[n].configure(fg_color="transparent")
        self.pages[name].grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        self.nav[name].configure(fg_color=ORANGE_DARK)
        if name == "Historial":
            self.render_history()

    def new_page(self, name):
        f = ctk.CTkFrame(self, fg_color="#eef0f4", corner_radius=0)
        self.pages[name] = f
        return f

    # --- Generador
    def build_generator(self):
        p = self.new_page("Generador")
        card = ctk.CTkFrame(p, fg_color="white", corner_radius=14)
        card.pack(fill="x", padx=24, pady=(20, 10))
        ctk.CTkLabel(card, text="Generador de Guiones Virales", font=("Segoe UI", 30, "bold"), text_color="#111").pack(pady=(16, 0))
        ctk.CTkLabel(card, text="Crea guiones de humor sobre motos con IA en segundos", font=("Segoe UI", 15), text_color="#555").pack()
        self.gen_btn = ctk.CTkButton(card, text="🏍  GENERAR GUION — HUMOR MOTOS · EDICIÓN IA", height=56,
                                     font=("Segoe UI", 19, "bold"), fg_color=ORANGE, hover_color="#e04e00",
                                     corner_radius=10, command=self.on_generate)
        self.gen_btn.pack(fill="x", padx=60, pady=(14, 6))
        ctk.CTkLabel(card, text="⚡ Powered by Google Gemini · ~15 segundos", text_color="#555", font=("Segoe UI", 12)).pack(pady=(0, 14))

        opts = ctk.CTkFrame(p, fg_color="white", corner_radius=12)
        opts.pack(fill="x", padx=24, pady=6)
        ctk.CTkLabel(opts, text="Tono:", font=("Segoe UI", 13, "bold"), text_color="#111").pack(side="left", padx=(16, 6), pady=12)
        self.tone = ctk.CTkOptionMenu(opts, values=TONES, fg_color="#f3f4f6", text_color="#111", button_color="#d1d5db",
                                      button_hover_color="#bfc3ca", width=170)
        self.tone.pack(side="left", padx=4)
        ctk.CTkLabel(opts, text="Duración:", font=("Segoe UI", 13, "bold"), text_color="#111").pack(side="left", padx=(24, 6))
        self.duration = ctk.CTkOptionMenu(opts, values=DURATIONS, fg_color="#f3f4f6", text_color="#111", button_color="#d1d5db",
                                          button_hover_color="#bfc3ca", width=120)
        self.duration.set("Reel 30s")
        self.duration.pack(side="left", padx=4)
        self.tiktok = ctk.CTkSwitch(opts, text="Estilo viral TikTok", text_color="#111", progress_color="#2563eb")
        self.tiktok.select()
        self.tiktok.pack(side="right", padx=16)

        out = ctk.CTkFrame(p, fg_color="white", corner_radius=12)
        out.pack(fill="both", expand=True, padx=24, pady=(6, 18))
        head = ctk.CTkFrame(out, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(head, text="📄  Guion generado", font=("Segoe UI", 16, "bold"), text_color="#111").pack(side="left")
        self.tokens_label = ctk.CTkLabel(head, text="", text_color="#777")
        self.tokens_label.pack(side="right", padx=(10, 0))
        for txt, cmd in (("🔄 Regenerar", self.on_generate), ("⬇ Descargar .txt", self.on_download), ("📋 Copiar", self.on_copy)):
            ctk.CTkButton(head, text=txt, width=120, fg_color="#f3f4f6", text_color="#111", hover_color="#e5e7eb",
                          border_width=1, border_color="#d1d5db", command=cmd).pack(side="right", padx=4)

        self.box = ctk.CTkTextbox(out, fg_color="white", text_color="#111", font=("Segoe UI", 15), wrap="word")
        self.box.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        t = self.box._textbox
        t.tag_config("l_texto", background="#1e88e5", foreground="white", font=("Segoe UI", 12, "bold"))
        t.tag_config("l_voz", background="#ff8a65", foreground="white", font=("Segoe UI", 12, "bold"))
        t.tag_config("l_pant", background="#2e9e1f", foreground="white", font=("Segoe UI", 12, "bold"))
        self.placeholder()

    def placeholder(self):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", "\n\n        🏍  Tu guion aparecerá aquí\n        Pulsa el botón de arriba para comenzar")
        self.box.configure(state="disabled")

    def render_script(self, text):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        t = self.box._textbox
        for line in text.splitlines():
            up = line.strip().upper()
            tag = None
            if up.startswith("TEXTO EN PANTALLA"):
                tag = "l_texto"
            elif up.startswith("VOZ OFF"):
                tag = "l_voz"
            elif up.startswith("LO QUE SE MUESTRA"):
                tag = "l_pant"
            if tag and ":" in line:
                label, rest = line.split(":", 1)
                t.insert("end", f" {label.strip()} ", tag)
                t.insert("end", "\n")
                if rest.strip():
                    t.insert("end", rest.strip() + "\n")
            elif tag:
                t.insert("end", f" {line.strip()} ", tag)
                t.insert("end", "\n")
            else:
                t.insert("end", line + "\n")
        self.box.configure(state="disabled")

    def on_generate(self):
        if not self.connected():
            messagebox.showwarning(APP_NAME, "Primero conecta tu cuenta de Google o una API Key en Configuración.")
            self.show("Configuración")
            return
        self.gen_btn.configure(state="disabled", text="⏳  Generando guion...")
        self.set_status("Generando con Gemini...", "#d97706")
        tone, dur, tk = self.tone.get(), self.duration.get(), bool(self.tiktok.get())
        start = datetime.now()

        def work():
            return generate_script(self.cfg, tone, dur, tk)

        def done(res, err):
            self.gen_btn.configure(state="normal", text="🏍  GENERAR GUION — HUMOR MOTOS · EDICIÓN IA")
            if err:
                self.set_status("Error", "#dc2626")
                messagebox.showerror(APP_NAME, str(err))
                return
            text, tokens = res
            self.last_script = text
            secs = int((datetime.now() - start).total_seconds())
            self.tokens_label.configure(text=f"🪙 {tokens:,} tokens · {secs}s")
            self.render_script(text)
            self.history.insert(0, {"date": datetime.now().strftime("%d/%m/%Y %H:%M"), "tone": tone, "duration": dur, "script": text})
            self.history = self.history[:100]
            save_json(HISTORY_FILE, self.history)
            self.set_status("Listo")

        self.run_bg(work, done)

    def on_copy(self):
        if self.last_script:
            self.clipboard_clear()
            self.clipboard_append(self.last_script)
            self.set_status("Guion copiado")

    def on_download(self):
        if not self.last_script:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Texto", "*.txt")],
                                            initialfile=f"guion_moto_{datetime.now():%Y%m%d_%H%M}.txt")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.last_script)
            self.set_status("Guion guardado")

    # --- Configuración
    def build_settings(self):
        p = self.new_page("Configuración")
        sc = ctk.CTkScrollableFrame(p, fg_color="#eef0f4")
        sc.pack(fill="both", expand=True, padx=14, pady=10)

        g = ctk.CTkFrame(sc, fg_color="white", corner_radius=12)
        g.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(g, text="🇬  Cuenta de Google (Recomendado)", font=("Segoe UI", 20, "bold"), text_color="#111").pack(anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(g, text="Conecta tu cuenta para usar Gemini AI sin API Key", text_color="#555").pack(anchor="w", padx=20)
        row = ctk.CTkFrame(g, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(10, 0))
        ctk.CTkButton(row, text="📄 Seleccionar client_secret.json", fg_color="#f3f4f6", text_color="#111", hover_color="#e5e7eb",
                      border_width=1, border_color="#d1d5db", command=self.pick_secret).pack(side="left")
        self.secret_label = ctk.CTkLabel(row, text="", text_color="#555")
        self.secret_label.pack(side="left", padx=10)
        ctk.CTkButton(g, text="Iniciar sesión con Google", height=48, font=("Segoe UI", 17, "bold"), fg_color="#0b5ed7",
                      hover_color="#0a4fb5", command=self.on_google).pack(fill="x", padx=20, pady=10)
        prow = ctk.CTkFrame(g, fg_color="transparent")
        prow.pack(fill="x", padx=20)
        ctk.CTkLabel(prow, text="ID de proyecto de Google Cloud (opcional):", text_color="#555").pack(side="left")
        self.project_entry = ctk.CTkEntry(prow, width=220, text_color="#111", fg_color="white", border_color="#d1d5db")
        self.project_entry.pack(side="left", padx=8)
        self.google_state = ctk.CTkLabel(g, text="", font=("Segoe UI", 14, "bold"))
        self.google_state.pack(pady=(8, 14))

        ctk.CTkLabel(sc, text="— O —", text_color="#333", font=("Segoe UI", 14, "bold")).pack(pady=2)

        a = ctk.CTkFrame(sc, fg_color="white", corner_radius=12)
        a.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(a, text="✦  API Key de Gemini (Alternativa)", font=("Segoe UI", 20, "bold"), text_color="#111").pack(anchor="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(a, text="API Key de Google Gemini", text_color="#111").pack(anchor="w", padx=20)
        krow = ctk.CTkFrame(a, fg_color="transparent")
        krow.pack(fill="x", padx=20, pady=4)
        self.key_entry = ctk.CTkEntry(krow, placeholder_text="AIzaSy...", show="•", height=40, text_color="#111", fg_color="white", border_color="#d1d5db")
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.eye = ctk.CTkButton(krow, text="👁", width=40, height=40, fg_color="#f3f4f6", text_color="#111", hover_color="#e5e7eb", command=self.toggle_key)
        self.eye.pack(side="left", padx=(6, 0))
        link = ctk.CTkLabel(a, text="¿Cómo obtener una API Key? ↗", text_color=ORANGE, cursor="hand2", font=("Segoe UI", 13, "underline"))
        link.pack(anchor="w", padx=20)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/app/apikey"))
        vrow = ctk.CTkFrame(a, fg_color="transparent")
        vrow.pack(fill="x", padx=20, pady=(10, 16))
        ctk.CTkButton(vrow, text="Validar API Key", fg_color="white", text_color=ORANGE, border_width=2, border_color=ORANGE,
                      hover_color="#fff3ec", command=self.on_validate).pack(side="left")
        self.key_state = ctk.CTkLabel(vrow, text="", font=("Segoe UI", 14, "bold"))
        self.key_state.pack(side="left", padx=12)

        m = ctk.CTkFrame(sc, fg_color="white", corner_radius=12)
        m.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(m, text="Modelo de Gemini:", text_color="#111", font=("Segoe UI", 14, "bold")).pack(side="left", padx=20, pady=14)
        self.model_menu = ctk.CTkOptionMenu(m, values=MODELS, fg_color="#f3f4f6", text_color="#111", button_color="#d1d5db", button_hover_color="#bfc3ca")
        self.model_menu.pack(side="left")

        foot = ctk.CTkFrame(sc, fg_color="transparent")
        foot.pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(foot, text="💾  Guardar configuración", height=42, fg_color=ORANGE, hover_color="#e04e00",
                      font=("Segoe UI", 14, "bold"), command=self.on_save).pack(side="right")
        ctk.CTkButton(foot, text="Cancelar", height=42, fg_color="white", text_color="#111", border_width=1, border_color="#9ca3af",
                      hover_color="#f3f4f6", command=self.load_settings_ui).pack(side="right", padx=8)
        self.load_settings_ui()

    def load_settings_ui(self):
        self.key_entry.delete(0, "end")
        self.key_entry.insert(0, self.cfg.get("api_key", ""))
        self.project_entry.delete(0, "end")
        self.project_entry.insert(0, self.cfg.get("project", ""))
        self.model_menu.set(self.cfg.get("model", MODELS[0]))
        self.secret_label.configure(text="✔ cargado" if os.path.exists(CLIENT_SECRET_FILE) else "(falta)")
        self.refresh_connection()

    def toggle_key(self):
        self.key_entry.configure(show="" if self.key_entry.cget("show") else "•")

    def pick_secret(self):
        path = filedialog.askopenfilename(title="client_secret.json", filetypes=[("JSON", "*.json")])
        if path:
            shutil.copy(path, CLIENT_SECRET_FILE)
            self.secret_label.configure(text="✔ cargado")

    def on_google(self):
        self.set_status("Esperando inicio de sesión en el navegador...", "#d97706")
        self.google_state.configure(text="Abriendo navegador...", text_color="#d97706")

        def done(email, err):
            if err:
                self.google_state.configure(text="No conectado", text_color="#dc2626")
                self.set_status("Error", "#dc2626")
                messagebox.showerror(APP_NAME, f"No se pudo iniciar sesión:\n{err}")
                return
            self.cfg.update(auth="google", email=email, project=self.project_entry.get().strip())
            save_json(CONFIG_FILE, self.cfg)
            self.refresh_connection()
            self.set_status("Cuenta conectada")

        self.run_bg(google_login, done)

    def on_validate(self):
        key = self.key_entry.get().strip()
        if not key:
            self.key_state.configure(text="Escribe una API Key", text_color="#dc2626")
            return
        self.key_state.configure(text="Validando...", text_color="#d97706")

        def done(ok, err):
            if err or not ok:
                self.key_state.configure(text="✖ API Key inválida", text_color="#dc2626")
            else:
                self.key_state.configure(text="✔ API Key válida", text_color="#16a34a")

        self.run_bg(lambda: validate_api_key(key), done)

    def on_save(self):
        key = self.key_entry.get().strip()
        self.cfg["api_key"] = key
        self.cfg["project"] = self.project_entry.get().strip()
        self.cfg["model"] = self.model_menu.get()
        if self.cfg.get("auth") != "google" or not os.path.exists(TOKEN_FILE):
            self.cfg["auth"] = "apikey" if key else "none"
        save_json(CONFIG_FILE, self.cfg)
        self.refresh_connection()
        messagebox.showinfo(APP_NAME, "Configuración guardada.")
        self.show("Generador")

    def refresh_connection(self):
        ok = self.connected()
        if ok:
            self.conn_label.configure(text="●  Gemini conectado", text_color="#22c55e", fg_color="#0f2a17")
        else:
            self.conn_label.configure(text="●  Sin conexión", text_color="#ef4444", fg_color="#2a1010")
        if self.cfg.get("auth") == "google" and os.path.exists(TOKEN_FILE):
            self.google_state.configure(text=f"✔ Conectado: {self.cfg.get('email', '')}", text_color="#16a34a")
            self.user_label.configure(text=f"👤  {self.cfg.get('email', '')}")
        else:
            self.google_state.configure(text="● No conectado", text_color="#dc2626")
            self.user_label.configure(text="👤  API Key" if ok else "👤  Sin cuenta conectada")
        self.model_label.configure(text=f"{self.cfg.get('model', MODELS[0])} · v{VERSION}")

    # --- Historial
    def build_history(self):
        p = self.new_page("Historial")
        ctk.CTkLabel(p, text="Historial de guiones", font=("Segoe UI", 26, "bold"), text_color="#111").pack(anchor="w", padx=24, pady=(20, 6))
        self.hist_frame = ctk.CTkScrollableFrame(p, fg_color="#eef0f4")
        self.hist_frame.pack(fill="both", expand=True, padx=14, pady=6)

    def render_history(self):
        for w in self.hist_frame.winfo_children():
            w.destroy()
        if not self.history:
            ctk.CTkLabel(self.hist_frame, text="Aún no has generado guiones.", text_color="#555").pack(pady=30)
            return
        for item in self.history:
            row = ctk.CTkFrame(self.hist_frame, fg_color="white", corner_radius=10)
            row.pack(fill="x", padx=8, pady=5)
            first = next((l for l in item["script"].splitlines() if l.strip() and ":" not in l[:3]), item["script"][:60])
            ctk.CTkLabel(row, text=f"{item['date']} · {item['tone']} · {item['duration']}", text_color="#777", font=("Segoe UI", 12)).pack(anchor="w", padx=14, pady=(8, 0))
            ctk.CTkLabel(row, text=first[:90], text_color="#111", font=("Segoe UI", 14, "bold"), anchor="w").pack(anchor="w", padx=14)
            ctk.CTkButton(row, text="Abrir", width=80, fg_color=ORANGE, hover_color="#e04e00",
                          command=lambda s=item["script"]: self.open_history(s)).pack(anchor="e", padx=14, pady=(0, 8))

    def open_history(self, script):
        self.last_script = script
        self.render_script(script)
        self.tokens_label.configure(text="")
        self.show("Generador")

    # --- Acerca de
    def build_about(self):
        p = self.new_page("Acerca de")
        ctk.CTkLabel(p, text=f"{APP_NAME} v{VERSION}", font=("Segoe UI", 28, "bold"), text_color="#111").pack(pady=(60, 6))
        ctk.CTkLabel(p, text="Generador de guiones virales de humor sobre motos.\nPowered by Google Gemini.",
                     font=("Segoe UI", 15), text_color="#555").pack()
        ctk.CTkLabel(p, text=f"Datos guardados en:\n{DATA_DIR}", font=("Segoe UI", 12), text_color="#777").pack(pady=20)


if __name__ == "__main__":
    App().mainloop()
