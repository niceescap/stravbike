import os
import json
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
import numpy as np
from io import BytesIO
from PIL import Image

# ── Constantes d'affichage (Identité visuelle FJC) ───────────────────────────
DARK_TEXT    = "#1A1A2E"
GRID_GRAY    = "#D0D0D0"
BLADE_WIDTH  = 0.32
FIG_SIZE     = (12, 12)

# Tranches inversées (Zmax au centre, Z1 à la périphérie)
DURATION_MAP_POWER = ["Z7", "Z6", "Z5", "Z4", "Z3", "Z2", "Z1"]
DURATION_MAP_HR    = ["Z5", "Z4", "Z3", "Z2", "Z1"]

def parse_raw_string(raw_str):
    """Extrait proprement les couples (min, max) de la chaîne brute Strava"""
    # Capture tous les patterns ZoneRange(max=X, min=Y) ou vice-versa
    pairs = re.findall(r'ZoneRange\((?:max=(-?\d+),\s*min=(\d+)|min=(\d+),\s*max=(-?\d+))\)', raw_str)
    zones_list = []
    for p in pairs:
        # Récupération des groupes selon l'ordre capturé par la regex
        mx = p[0] if p[0] else p[3]
        mn = p[1] if p[1] else p[2]
        zones_list.append({"min": int(mn), "max": int(mx)})
    return zones_list

def build_fused_mesh(radii, values, base_angle, width_factor, scale_factor):
    R_mesh, Width_mesh = np.meshgrid(radii, np.linspace(-width_factor, width_factor, 26))
    val_mesh = np.tile(values, (26, 1))
    Theta_mesh = base_angle + Width_mesh * (0.4 + R_mesh * 0.8)
    X = R_mesh * np.cos(Theta_mesh)
    Y = R_mesh * np.sin(Theta_mesh)
    Z = val_mesh * scale_factor
    return X, Y, Z

def generate_artichoke_from_strava(json_path, output_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    weight = data.get("poids_athlete", 71.0)

    # 1. Extraction et conversion Puissance (Watts -> W/kg)
    raw_power = parse_raw_string(data.get("raw_power_string", ""))
    power_values = []
    for z in raw_power:
        mx = z["max"]
        if mx == -1: 
            mx = z["min"] * 1.5  # Fallback pour le plafond de la Z7
        power_values.append(mx / weight)
    
    # Inversion pour le tracé (centre -> extérieur)
    power_values.reverse()
    radii_power = np.linspace(0.15, 1.0, len(power_values))

    # 2. Extraction Cardio (BPM)
    raw_hr = parse_raw_string(data.get("raw_hr_string", ""))
    hr_values = []
    for z in raw_hr:
        mx = z["max"]
        if mx == -1: 
            mx = z["min"] * 1.05  # Fallback pour le plafond de la Z5
        hr_values.append(mx)
        
    hr_values.reverse()
    radii_hr = np.linspace(0.15, 1.0, len(hr_values))

    # Configuration des quadrants actifs
    quadrants = {
        "power":      {"values": np.array(power_values), "radii": radii_power, "maps": DURATION_MAP_POWER, "angle": np.pi/2,  "label": "PUISSANCE (W/kg)", "cmap": cm.Wistia,   "scale": 0.25, "fmt": ".1f"},
        "heart_rate": {"values": np.array(hr_values),    "radii": radii_hr,    "maps": DURATION_MAP_HR,    "angle": -np.pi/2, "label": "CARDIO (bpm)",     "cmap": cm.RdPu,     "scale": 0.02, "fmt": ".0f"},
    }

    # Initialisation de la scène Matplotlib 3D
    fig = plt.figure(figsize=FIG_SIZE, facecolor="none")
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor("none")

    # ── Trame de fond fixe ────────────────────────────────
    for q in quadrants.values():
        if len(q["values"]) == 0: continue
        universal_profile = np.linspace(20, 100, len(q["values"]))
        Xg, Yg, Zg = build_fused_mesh(q["radii"], universal_profile, q["angle"], BLADE_WIDTH * 1.25, q["scale"])
        ax.plot_wireframe(Xg, Yg, Zg, rstride=5, cstride=4, color=GRID_GRAY, alpha=0.25, linewidth=0.7)

    # ── Génération des Pétales 3D ─────────────────────────
    for q in quadrants.values():
        if len(q["values"]) == 0: continue
        
        Xa, Ya, Za = build_fused_mesh(q["radii"], q["values"], q["angle"], BLADE_WIDTH, q["scale"])

        norm_Z = Za / (Za.max() if Za.max() > 0 else 1)
        colors_matrix = q["cmap"](norm_Z)
        for r_idx in range(len(q["radii"])):
            opacity = 0.98 - (q["radii"][r_idx] * 0.50)
            colors_matrix[:, r_idx, 3] = opacity

        ax.plot_surface(Xa, Ya, Za, facecolors=colors_matrix, linewidth=0, antialiased=True, shade=True)

        # Label de l'axe
        ax.text(1.15 * np.cos(q["angle"]), 1.15 * np.sin(q["angle"]), q["values"][-1] * q["scale"],
                q["label"], color=DARK_TEXT, fontsize=10, fontweight="bold", ha="center", va="center")

        # Badges d'étiquettes de zone
        label_angle_offset = 0.25
        for idx in range(len(q["values"])):
            val_str = f"{q['values'][idx]:{q['fmt']}}"
            label_text = f"{q['maps'][idx]}\n{val_str}"
            current_label_angle = q["angle"] + label_angle_offset
            x_pos = q["radii"][idx] * np.cos(current_label_angle)
            y_pos = q["radii"][idx] * np.sin(current_label_angle)
            z_pos = q["values"][idx] * q["scale"] + (Za.max() * 0.04)
            
            ax.text(x_pos, y_pos, z_pos, label_text, color=DARK_TEXT,
                    fontsize=8, fontweight="700", ha="center", va="center",
                    bbox=dict(boxstyle="square,pad=0.2", facecolor="white", edgecolor="#EAF0F6", linewidth=0.5, alpha=0.85),
                    fontfamily="DejaVu Sans", zorder=20)

    # ── Ajustement caméra et rendu final ──────────────────
    ax.view_init(elev=32, azim=-45)
    ax.axis('off')
    ax.set_box_aspect([1, 1, 0.42])
    plt.tight_layout()

    # Création du dossier de stockage si inexistant
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Sauvegarde optimisée avec Pillow pour gérer la transparence alpha
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="none", transparent=True, dpi=150)
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")
    img.save(str(output_path), format="PNG")

if __name__ == "__main__":
    out_img = "data/storage/profiles/athlete_profile_3d.png"
    generate_artichoke_from_strava("strava_athlete_data.json", out_img)
    print(f"🎨 Étoile Artichaut 3D générée avec succès -> {out_img}")
