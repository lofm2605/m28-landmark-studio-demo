import base64
import datetime
import html
import os
import time

import day_cvat
import dot_anh
import nap_anh
from nap_anh import RunError

INTERVAL = 30
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(TOOL_DIR, "assets")
ASSET_TYPES = (("yasuo.gif", "image/gif"), ("yasuo.webp", "image/webp"), ("yasuo.png", "image/png"), ("yasuo.jpg", "image/jpeg"))
ASSET_MAX = 6 * 1024 * 1024
PARTIAL = ("dang_tao", "da_tao", "da_nhap", "hong")
STATE_VI = {"new": "Mới", "in progress": "Đang sửa", "rejected": "Bị trả lại", "completed": "Xong"}
KIND_VI = {"nhan": "Nhận", "gan_tay": "Sửa nhãn"}


def _e(x):
    return html.escape(str(x), quote=True)


def asset_uri(asset_dir=None):
    d = ASSET_DIR if asset_dir is None else asset_dir
    for name, mime in ASSET_TYPES:
        p = os.path.join(d, name)
        try:
            if os.path.isfile(p) and 0 < os.path.getsize(p) <= ASSET_MAX:
                with open(p, "rb") as f:
                    return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")
        except OSError:
            continue
    return None


DEFS_SVG = """
  <defs>
    <clipPath id="cvClip"><rect width="480" height="240" rx="14"/></clipPath>
    <clipPath id="cvCutTop"><polygon points="300,-60 480,-60 480,61.0 300,153.5"/></clipPath>
    <clipPath id="cvCutBot"><polygon points="300,153.5 480,61.0 480,260 300,260"/></clipPath>
    <clipPath id="cvGround"><rect x="-200" y="-200" width="900" height="409.5"/></clipPath>
    <linearGradient id="cvSky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0c1d3d"/><stop offset=".65" stop-color="#0a1430"/>
      <stop offset="1" stop-color="#070d1c"/></linearGradient>
    <radialGradient id="cvMoon" cx="40%" cy="40%" r="60%"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#bae6fd"/></radialGradient>
    <radialGradient id="cvHalo" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#7dd3fc" stop-opacity=".35"/>
      <stop offset="1" stop-color="#7dd3fc" stop-opacity="0"/></radialGradient>
    <linearGradient id="cvBlade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#cbd5e1"/><stop offset=".7" stop-color="#f8fafc"/>
      <stop offset="1" stop-color="#7dd3fc"/></linearGradient>
    <linearGradient id="cvCloth" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d4ed8"/><stop offset="1" stop-color="#0f1f3d"/></linearGradient>
    <linearGradient id="cvStreak" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#22d3ee" stop-opacity="0"/>
      <stop offset=".6" stop-color="#7dd3fc" stop-opacity=".8"/><stop offset="1" stop-color="#f0f9ff"/></linearGradient>
    <radialGradient id="cvTorGlow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#22d3ee" stop-opacity=".3"/>
      <stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></radialGradient>
    <linearGradient id="dmStraw" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f1cf7a"/><stop offset="1" stop-color="#b9813a"/></linearGradient>
    <linearGradient id="dmWood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#9a6634"/><stop offset="1" stop-color="#5b3a1e"/></linearGradient>
  </defs>
"""

SCENE_SVG = """
  <rect width="480" height="240" fill="url(#cvSky)"/>
  <circle cx="70" cy="54" r="56" fill="url(#cvHalo)"/>
  <circle cx="70" cy="54" r="22" fill="url(#cvMoon)"/>
  <circle cx="62" cy="48" r="4" fill="#cbd5e1" opacity=".5"/><circle cx="78" cy="62" r="3" fill="#cbd5e1" opacity=".45"/>
  <g class="cv-stars" fill="#e0f2fe">
    <circle cx="150" cy="24" r="1.2"/><circle cx="214" cy="46" r="1"/><circle cx="268" cy="18" r="1.4"/><circle cx="322" cy="40" r="1"/>
    <circle cx="428" cy="22" r="1.3"/><circle cx="456" cy="58" r="1"/><circle cx="24" cy="110" r="1"/><circle cx="196" cy="84" r="1.1"/>
  </g>
  <path d="M0 168 L44 138 L84 156 L134 116 L182 148 L232 124 L290 158 L340 130 L398 154 L448 126 L480 144 V240 H0 Z" fill="#0e1d3a"/>
  <path d="M0 192 L62 170 L122 186 L192 162 L262 184 L332 168 L402 188 L480 172 V240 H0 Z" fill="#0a152b"/>
  <rect y="209" width="480" height="31" fill="#060b16"/>
  <path d="M0 209.5 H480" stroke="#1e3a5f" stroke-width="1.2" opacity=".8"/>
  <path d="M30 209 l3 -6 l2 6 M220 209 l2 -5 l3 5 M250 209 l3 -7 l2 7 M300 209 l2 -5 l2 5 M446 209 l3 -6 l2 6" stroke="#1e3a5f" stroke-width="1.4"
    fill="none" stroke-linecap="round"/>
  <g class="cv-petal" style="--x0:-20px;--y0:30px;--x1:500px;--y1:150px;animation-duration:7s"><path d="M0 0 C3 -4 8 -4 9 0 C8 4 3 4 0 0 Z" fill="#fbcfe8"/></g>
  <g class="cv-petal" style="--x0:-20px;--y0:90px;--x1:500px;--y1:190px;animation-duration:9s;animation-delay:-3s"><path d="M0 0 C3 -4 8 -4 9 0 C8 4 3 4 0 0 Z" fill="#f9a8d4"/></g>
  <rect class="cv-dark" width="480" height="240" fill="#020409"/>
"""

YASUO_SVG = """
  <g class="cv-ys">
    <path class="cv-tail" d="M124 62 C106 52 86 54 70 62 C60 68 50 68 38 62 C50 78 70 78 84 72 C76 84 66 92 54 98 C76 96 96 84 112 72 C118 70 122 70 126 70 Z"
      fill="#16213d" stroke="#38bdf8" stroke-opacity=".55" stroke-width="1.2" stroke-linejoin="round"/>
    <path class="cv-scarf" d="M132 88 C112 86 96 92 80 104 C70 112 58 114 46 110 C58 124 80 120 94 112 C108 104 120 100 134 98 Z" fill="#0ea5e9" opacity=".9"/>
    <g class="cv-rear">
      <path d="M124 98 L111 104 L107.6 114.8" fill="none" stroke="#38bdf8" stroke-opacity=".4" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M124 98 L111 104 L107.6 114.8" fill="none" stroke="#0f1a30" stroke-width="7.5" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="107.6" cy="114.8" r="3.6" fill="#1e293b" stroke="#38bdf8" stroke-opacity=".5" stroke-width="1"/>
    </g>
    <g class="cv-upper cv-back">
    <g class="cv-sheath">
      <path d="M123.6 114.8 L5.6 114.8" fill="none" stroke="#38bdf8" stroke-opacity=".4" stroke-width="11" stroke-linecap="round"/>
      <path d="M123.6 114.8 L5.6 114.8" fill="none" stroke="#111c33" stroke-width="8.4" stroke-linecap="round"/>
      <path d="M123.6 114.8 L5.6 114.8" fill="none" stroke="#1e3a5f" stroke-width="2.2" stroke-linecap="round" opacity=".8"/>
      <path d="M123.6 119.8 L123.6 109.8" stroke="#facc15" stroke-width="4" stroke-linecap="round"/>
      <path d="M74.0 118.8 L74.0 110.8" stroke="#facc15" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M36.3 118.6 L36.3 111.0" stroke="#facc15" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M7.4 119.2 L7.4 110.4" stroke="#facc15" stroke-width="3.6" stroke-linecap="round"/>
      <path d="M64.6 118.8 C70.6 136.8 66.6 148.8 72.6 160.8" fill="none" stroke="#0ea5e9" stroke-width="1.8" stroke-linecap="round"/>
    </g>
      <g class="cv-arm cv-rigback"><g class="cv-fore">
        <g class="cv-swb"><path d="M162 111 L186 104" fill="none" stroke="#38bdf8" stroke-opacity=".5" stroke-width="10" stroke-linecap="round"/>
        <path d="M162 111 L186 104" fill="none" stroke="#13213d" stroke-width="7.5" stroke-linecap="round"/>
        <path d="M169 109 L177 106.8" stroke="#38bdf8" stroke-opacity=".75" stroke-width="2.2" stroke-linecap="round"/></g>
      <g class="cv-hand"><g class="cv-swb">
        <path d="M181 104.4 L194 104.4" stroke="#334155" stroke-width="4.6" stroke-linecap="round"/>
        <circle cx="186" cy="104.2" r="4.3" fill="#1e293b" stroke="#7dd3fc" stroke-opacity=".6" stroke-width="1"/>
        <path d="M193 99.8 L195.2 109" stroke="#facc15" stroke-width="3.8" stroke-linecap="round"/>
      <g class="cv-blade">
        <path d="M195 102.4 L286 102 L297 104.5 L286 106.8 L195 107 Z" fill="url(#cvBlade)"/>
        <path d="M197 103.4 L286 103.1" stroke="#ffffff" stroke-width=".8" opacity=".9"/>
        <path class="cv-drawflash" d="M195 104.5 L297 104.5" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>
      </g></g></g></g></g>
    </g>
    <g class="cv-legs" clip-path="url(#cvGround)">
    <path d="M120 140 L104 172 L86 206" fill="none" stroke="#38bdf8" stroke-opacity=".35" stroke-width="14.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M120 140 L104 172 L86 206" fill="none" stroke="#0f1a30" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M134 140 L158 168 L166 206" fill="none" stroke="#38bdf8" stroke-opacity=".35" stroke-width="14.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M134 140 L158 168 L166 206" fill="none" stroke="#0f1a30" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M76 207.5 H96 M160 207.5 H183" stroke="#0f1a30" stroke-width="6" stroke-linecap="round"/>
    </g>
    <path d="M112 132 L146 132 L172 190 L154 186 L132 156 L110 190 L88 194 Z" fill="url(#cvCloth)" stroke="#38bdf8" stroke-opacity=".6" stroke-width="1.2"
      stroke-linejoin="round"/>
    <g class="cv-upper">
    <path d="M114 134 C110 108 116 92 126 86 L150 88 C156 104 152 122 146 134 Z" fill="#111c33" stroke="#38bdf8" stroke-opacity=".55" stroke-width="1.2"/>
    <path d="M128 90 L142 132" stroke="#1e3a5f" stroke-width="3" stroke-linecap="round"/>
    <path class="cv-sash" d="M114 132 C100 138 90 150 84 164 C96 156 106 148 118 138 Z" fill="#0284c7"/>
    <rect x="111" y="127" width="37" height="8" rx="2" fill="#38bdf8"/>
    <circle cx="136" cy="74" r="11.5" fill="#111c33" stroke="#38bdf8" stroke-opacity=".55" stroke-width="1.2"/>
    <path d="M124 70 C122 58 132 52 142 55 C150 58 152 66 148 72 C144 66 138 64 130 66 Z" fill="#16213d"/>
    <path d="M146 63 L153 72 L145 69 Z" fill="#16213d"/>
    <circle cx="124" cy="66" r="2.6" fill="#38bdf8"/>
    <path d="M142 73 L149 74" stroke="#e0f2fe" stroke-width="1.6" stroke-linecap="round"/>
    <g class="cv-arm">
      <path d="M144 95 L162 111" fill="none" stroke="#38bdf8" stroke-opacity=".5" stroke-width="11" stroke-linecap="round"/>
      <path d="M144 95 L162 111" fill="none" stroke="#13213d" stroke-width="8.5" stroke-linecap="round"/>
      <g class="cv-fore">
        <g class="cv-swf"><path d="M162 111 L186 104" fill="none" stroke="#38bdf8" stroke-opacity=".5" stroke-width="10" stroke-linecap="round"/>
        <path d="M162 111 L186 104" fill="none" stroke="#13213d" stroke-width="7.5" stroke-linecap="round"/>
        <path d="M169 109 L177 106.8" stroke="#38bdf8" stroke-opacity=".75" stroke-width="2.2" stroke-linecap="round"/></g>
        <g class="cv-hand">
          <g class="cv-swf"><path d="M181 104.4 L194 104.4" stroke="#334155" stroke-width="4.6" stroke-linecap="round"/>
          <circle cx="186" cy="104.2" r="4.3" fill="#1e293b" stroke="#7dd3fc" stroke-opacity=".6" stroke-width="1"/></g>
          <g class="cv-swf"><path d="M193 99.8 L195.2 109" stroke="#facc15" stroke-width="3.8" stroke-linecap="round"/></g>
          <g class="cv-swf"><g class="cv-blade">
            <g class="cv-q3glow"><path d="M198 104.5 L292 104.5" stroke="#22d3ee" stroke-opacity=".28" stroke-width="30" stroke-linecap="round"/><path d="M198 104.5 L292 104.5" stroke="#67e8f9" stroke-opacity=".6" stroke-width="13" stroke-linecap="round"/></g>
            <path d="M195 102.4 L286 102 L297 104.5 L286 106.8 L195 107 Z" fill="url(#cvBlade)"/>
            <path d="M197 103.4 L286 103.1" stroke="#ffffff" stroke-width=".8" opacity=".9"/>
            <path class="cv-glint" d="M202 103.8 L222 103.6" stroke="#ffffff" stroke-width="3.6" stroke-linecap="round"/>
            <path class="cv-drawflash" d="M195 104.5 L297 104.5" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>
          </g></g>
        </g>
      </g>
      <circle cx="162" cy="111" r="4.9" fill="#13213d" stroke="#38bdf8" stroke-opacity=".5" stroke-width="1.2"/>
    </g>
    <g class="cv-mouth"><path d="M110.0 102.8 L112.0 111.8 L122.0 114.8 L112.0 117.8 L110.0 126.8 L108.0 117.8 L98.0 114.8 L108.0 111.8 Z" fill="#fef3c7"/><circle cx="110.0" cy="114.8" r="3.4" fill="#fff"/></g>
    <path d="M138 90 C152 78 170 84 174 96 C164 92 154 96 148 104 C144 98 140 94 138 90 Z" fill="#1e293b" stroke="#7dd3fc" stroke-width="1.4"
      stroke-linejoin="round"/>
    <path d="M146 90 C156 84 166 86 170 93" stroke="#7dd3fc" stroke-width="1" fill="none" opacity=".7"/>
    </g>
  </g>
"""

DUMMY_SVG = """
  <ellipse class="cv-dm-shadow" cx="380" cy="210.5" rx="34" ry="4.5" fill="#000" opacity=".5"/>
  <g class="cv-dummy">
    <path d="M354 208 H406" stroke="#4a2e15" stroke-width="6" stroke-linecap="round"/>
    <path d="M364 208 L380 194 L396 208" fill="none" stroke="#5b3a1e" stroke-width="4" stroke-linejoin="round"/>
    <rect x="377" y="54" width="6" height="154" rx="2" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <rect x="338" y="88" width="84" height="7" rx="3.5" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <path d="M340 91.5 L330 84 M340 91.5 L327 91.5 M340 91.5 L330 99 M420 91.5 L430 84 M420 91.5 L433 91.5 M420 91.5 L430 99" stroke="#e3b964"
      stroke-width="2" stroke-linecap="round"/>
    <rect x="358" y="82" width="44" height="66" rx="16" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M366 92 l3 8 M393 98 l-2 9 M368 128 l2 8 M391 130 l-3 7 M379 140 l1 5" stroke="#f8e3a8" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
    <path d="M359 96 Q380 101 401 96 M359 136 Q380 141 401 136" fill="none" stroke="#5b3a1e" stroke-width="2.5"/>
    <circle cx="380" cy="114" r="11" fill="#f8fafc"/><circle cx="380" cy="114" r="7.5" fill="#ef4444"/>
    <circle cx="380" cy="114" r="3.6" fill="#f8fafc"/><circle cx="380" cy="114" r="1.4" fill="#ef4444"/>
    <path d="M361 146 L364 160 L368 147 L372 162 L376 147 L380 163 L384 147 L388 162 L392 147 L396 160 L399 146 Z" fill="#c9933f" stroke="#6b4a1f"
      stroke-width=".8" stroke-linejoin="round"/>
    <circle cx="380" cy="64" r="14" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M373 51.5 L380 43 L387 51.5" fill="#c9933f" stroke="#6b4a1f" stroke-width=".8" stroke-linejoin="round"/>
    <path d="M372 60 l5 5 m0 -5 l-5 5 M383 60 l5 5 m0 -5 l-5 5" stroke="#3b2410" stroke-width="1.7" stroke-linecap="round"/>
    <path d="M373 71 H387 M375.5 69 v4 M380 69 v4 M384.5 69 v4" stroke="#3b2410" stroke-width="1.2" stroke-linecap="round"/>
    <g class="cv-dm-flash"><rect x="358" y="82" width="44" height="66" rx="16" fill="#fff"/><circle cx="380" cy="64" r="14" fill="#fff"/></g>
    <g transform="translate(380 112) rotate(40)"><g class="cv-cut cv-cut1"><path d="M-50 0 L50 0" stroke="#38bdf8" stroke-opacity=".35" stroke-width="9" stroke-linecap="round"/><path d="M-50 0 Q-8 -6 50 0 Q-8 2.6 -50 0 Z" fill="#f8fafc"/></g></g>
    <g transform="translate(380 112) rotate(-40)"><g class="cv-cut cv-cut2"><path d="M-50 0 L50 0" stroke="#38bdf8" stroke-opacity=".35" stroke-width="9" stroke-linecap="round"/><path d="M-50 0 Q-8 -6 50 0 Q-8 2.6 -50 0 Z" fill="#f8fafc"/></g></g>
    <text class="cv-tag" x="380" y="36" text-anchor="middle">CVAT</text>
  </g>
  <g class="cv-fdummy">
  <g class="cv-half cv-half-bot" clip-path="url(#cvCutBot)">
    <path d="M354 208 H406" stroke="#4a2e15" stroke-width="6" stroke-linecap="round"/>
    <path d="M364 208 L380 194 L396 208" fill="none" stroke="#5b3a1e" stroke-width="4" stroke-linejoin="round"/>
    <rect x="377" y="54" width="6" height="154" rx="2" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <rect x="338" y="88" width="84" height="7" rx="3.5" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <path d="M340 91.5 L330 84 M340 91.5 L327 91.5 M340 91.5 L330 99 M420 91.5 L430 84 M420 91.5 L433 91.5 M420 91.5 L430 99" stroke="#e3b964"
      stroke-width="2" stroke-linecap="round"/>
    <rect x="358" y="82" width="44" height="66" rx="16" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M366 92 l3 8 M393 98 l-2 9 M368 128 l2 8 M391 130 l-3 7 M379 140 l1 5" stroke="#f8e3a8" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
    <path d="M359 96 Q380 101 401 96 M359 136 Q380 141 401 136" fill="none" stroke="#5b3a1e" stroke-width="2.5"/>
    <circle cx="380" cy="114" r="11" fill="#f8fafc"/><circle cx="380" cy="114" r="7.5" fill="#ef4444"/>
    <circle cx="380" cy="114" r="3.6" fill="#f8fafc"/><circle cx="380" cy="114" r="1.4" fill="#ef4444"/>
    <path d="M361 146 L364 160 L368 147 L372 162 L376 147 L380 163 L384 147 L388 162 L392 147 L396 160 L399 146 Z" fill="#c9933f" stroke="#6b4a1f"
      stroke-width=".8" stroke-linejoin="round"/>
    <circle cx="380" cy="64" r="14" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M373 51.5 L380 43 L387 51.5" fill="#c9933f" stroke="#6b4a1f" stroke-width=".8" stroke-linejoin="round"/>
    <path d="M372 60 l5 5 m0 -5 l-5 5 M383 60 l5 5 m0 -5 l-5 5" stroke="#3b2410" stroke-width="1.7" stroke-linecap="round"/>
    <path d="M373 71 H387 M375.5 69 v4 M380 69 v4 M384.5 69 v4" stroke="#3b2410" stroke-width="1.2" stroke-linecap="round"/>
  </g>
  <g class="cv-half cv-half-top" clip-path="url(#cvCutTop)">
    <path d="M354 208 H406" stroke="#4a2e15" stroke-width="6" stroke-linecap="round"/>
    <path d="M364 208 L380 194 L396 208" fill="none" stroke="#5b3a1e" stroke-width="4" stroke-linejoin="round"/>
    <rect x="377" y="54" width="6" height="154" rx="2" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <rect x="338" y="88" width="84" height="7" rx="3.5" fill="url(#dmWood)" stroke="#2e1a0b" stroke-width="1"/>
    <path d="M340 91.5 L330 84 M340 91.5 L327 91.5 M340 91.5 L330 99 M420 91.5 L430 84 M420 91.5 L433 91.5 M420 91.5 L430 99" stroke="#e3b964"
      stroke-width="2" stroke-linecap="round"/>
    <rect x="358" y="82" width="44" height="66" rx="16" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M366 92 l3 8 M393 98 l-2 9 M368 128 l2 8 M391 130 l-3 7 M379 140 l1 5" stroke="#f8e3a8" stroke-width="1.2" stroke-linecap="round" opacity=".75"/>
    <path d="M359 96 Q380 101 401 96 M359 136 Q380 141 401 136" fill="none" stroke="#5b3a1e" stroke-width="2.5"/>
    <circle cx="380" cy="114" r="11" fill="#f8fafc"/><circle cx="380" cy="114" r="7.5" fill="#ef4444"/>
    <circle cx="380" cy="114" r="3.6" fill="#f8fafc"/><circle cx="380" cy="114" r="1.4" fill="#ef4444"/>
    <path d="M361 146 L364 160 L368 147 L372 162 L376 147 L380 163 L384 147 L388 162 L392 147 L396 160 L399 146 Z" fill="#c9933f" stroke="#6b4a1f"
      stroke-width=".8" stroke-linejoin="round"/>
    <circle cx="380" cy="64" r="14" fill="url(#dmStraw)" stroke="#6b4a1f" stroke-width="1.4"/>
    <path d="M373 51.5 L380 43 L387 51.5" fill="#c9933f" stroke="#6b4a1f" stroke-width=".8" stroke-linejoin="round"/>
    <path d="M372 60 l5 5 m0 -5 l-5 5 M383 60 l5 5 m0 -5 l-5 5" stroke="#3b2410" stroke-width="1.7" stroke-linecap="round"/>
    <path d="M373 71 H387 M375.5 69 v4 M380 69 v4 M384.5 69 v4" stroke="#3b2410" stroke-width="1.2" stroke-linecap="round"/>
    <text class="cv-tag" x="380" y="36" text-anchor="middle">CVAT</text>
  </g>
  </g>
"""

FX_SVG = """
  <g class="cv-spark"><g transform="translate(366 104.5) scale(1.9) translate(-366 -104.5)"><path d="M366 90 L369.5 100 L380 96 L372 104 L382 110 L370.5 108.5 L368 120 L364 109 L352 111 L361 103.5 L354 95 L364 99.5 Z" fill="#fef3c7"/>
    <circle cx="366" cy="104.5" r="3.4" fill="#fff"/></g></g>
  <g class="cv-tor">
    <ellipse cx="300" cy="140" rx="40" ry="74" fill="url(#cvTorGlow)"/>
    <ellipse class="cv-ring" cx="300" cy="74" rx="36" ry="8"/><ellipse class="cv-ring" cx="300" cy="92" rx="31" ry="7.5"/>
    <ellipse class="cv-ring" cx="300" cy="110" rx="27" ry="7"/><ellipse class="cv-ring" cx="300" cy="128" rx="22" ry="6"/>
    <ellipse class="cv-ring" cx="300" cy="146" rx="18" ry="5.5"/><ellipse class="cv-ring" cx="300" cy="163" rx="14" ry="5"/>
    <ellipse class="cv-ring" cx="300" cy="179" rx="10" ry="4"/><ellipse class="cv-ring" cx="300" cy="193" rx="6.5" ry="3"/>
    <ellipse class="cv-ring" cx="300" cy="204" rx="3.5" ry="2"/>
    <path class="cv-swirl" d="M276 96 C292 84 316 88 322 102 M282 140 C294 130 310 132 314 144" fill="none" stroke="#f0f9ff" stroke-width="1.6"
      stroke-linecap="round"/>
  </g>
  <g class="cv-dust"><ellipse cx="362" cy="205" rx="11" ry="4.5"/><ellipse cx="398" cy="205" rx="11" ry="4.5"/><ellipse cx="380" cy="202" rx="15" ry="5.5"/></g>
  <g class="cv-blink"><ellipse cx="146" cy="124" rx="48" ry="70" fill="url(#cvTorGlow)"/>
    <path d="M114 92 L60 74 M112 124 L40 124 M114 156 L60 176 M174 96 L204 82 M176 154 L204 170" stroke="#e0f2fe" stroke-width="3" stroke-linecap="round"/>
    <circle cx="146" cy="124" r="24" fill="none" stroke="#7dd3fc" stroke-width="3.4"/></g>
  <g class="cv-dash"><path d="M176 100 L360 118 L176 134 Z" fill="url(#cvStreak)"/></g>
  <g class="cv-rfollow"><g transform="translate(380 116)">
    <g class="cv-rsl" style="--r:-62deg;--x:-14px;--y:-18px;animation-delay:0.000s"><path d="M-150 0 L150 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-150 0 Q-45 -8.4 30 -6.6 L150 0 Q30 6.6 -45 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:26deg;--x:10px;--y:14px;animation-delay:0.025s"><path d="M-140 0 L140 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-140 0 Q-42 -8.4 28 -6.6 L140 0 Q28 6.6 -42 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:-10deg;--x:0px;--y:-4px;animation-delay:0.050s"><path d="M-168 0 L168 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-168 0 Q-50 -8.4 34 -6.6 L168 0 Q34 6.6 -50 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:66deg;--x:-10px;--y:8px;animation-delay:0.075s"><path d="M-130 0 L130 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-130 0 Q-39 -8.4 26 -6.6 L130 0 Q26 6.6 -39 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:-82deg;--x:12px;--y:0px;animation-delay:0.100s"><path d="M-136 0 L136 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-136 0 Q-41 -8.4 27 -6.6 L136 0 Q27 6.6 -41 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:42deg;--x:-14px;--y:-10px;animation-delay:0.125s"><path d="M-150 0 L150 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-150 0 Q-45 -8.4 30 -6.6 L150 0 Q30 6.6 -45 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:-36deg;--x:8px;--y:16px;animation-delay:0.150s"><path d="M-146 0 L146 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-146 0 Q-44 -8.4 29 -6.6 L146 0 Q29 6.6 -44 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:84deg;--x:-4px;--y:-12px;animation-delay:0.175s"><path d="M-128 0 L128 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-128 0 Q-38 -8.4 26 -6.6 L128 0 Q26 6.6 -38 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:8deg;--x:0px;--y:20px;animation-delay:0.200s"><path d="M-160 0 L160 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-160 0 Q-48 -8.4 32 -6.6 L160 0 Q32 6.6 -48 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:-52deg;--x:14px;--y:-8px;animation-delay:0.225s"><path d="M-138 0 L138 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-138 0 Q-41 -8.4 28 -6.6 L138 0 Q28 6.6 -41 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:58deg;--x:-6px;--y:18px;animation-delay:0.250s"><path d="M-122 0 L122 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-122 0 Q-37 -8.4 24 -6.6 L122 0 Q24 6.6 -37 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rsl" style="--r:-24deg;--x:4px;--y:-16px;animation-delay:0.275s"><path d="M-154 0 L154 0" stroke="#22d3ee" stroke-opacity=".26" stroke-width="12" stroke-linecap="round"/><path d="M-154 0 Q-46 -8.4 31 -6.6 L154 0 Q31 6.6 -46 8.4 Z" fill="url(#cvStreak)"/></g>
    <g class="cv-rx"><path d="M-150 -88 L150 88 M-150 88 L150 -88" stroke="#f0f9ff" stroke-width="4" stroke-linecap="round"/>
      <path d="M-160 0 L160 0 M0 -110 L0 110" stroke="#7dd3fc" stroke-width="2.4" stroke-linecap="round" opacity=".8"/>
      <circle r="34" fill="#fff"/><circle r="62" fill="none" stroke="#7dd3fc" stroke-width="3.2"/><circle r="92" fill="none" stroke="#e0f2fe" stroke-width="1.6" opacity=".7"/></g>
  </g></g>
  <g class="cv-petal" style="--x0:-20px;--y0:60px;--x1:500px;--y1:120px;animation-duration:8s;animation-delay:-5s"><path d="M0 0 C3 -4 8 -4 9 0 C8 4 3 4 0 0 Z" fill="#fce7f3"/></g>
  <g transform="translate(196.0 135.0) rotate(-27.2)"><g class="cv-ecut"><path d="M-6 0 L105 0" stroke="#7dd3fc" stroke-opacity=".45" stroke-width="10" stroke-linecap="round"/><path d="M-6 0 L105 0" stroke="#ffffff" stroke-width="2.8" stroke-linecap="round"/></g></g>
"""

def art_html(img=None):
    fig = YASUO_SVG
    if img:
        fig = (f'<g class="cv-ys"><image href="{img}" x="34" y="40" width="190" height="170" preserveAspectRatio="xMidYMax meet"/></g>')
    return (f'<div class="cv-art"><svg class="cv-svg" viewBox="0 0 480 240" role="img" aria-label="Kiếm sĩ chọc hình nộm, nhát thứ ba ra lốc xoáy, rồi biến mất và chém quanh hình nộm như R của Yasuo; xong việc thì lướt qua chém đôi hình nộm">'
            f'{DEFS_SVG}<g clip-path="url(#cvClip)">{SCENE_SVG}{DUMMY_SVG}{fig}{FX_SVG}</g></svg></div>')


def hero_html(img=None):
    return (f'<div class="cv-hero">{art_html(img)}<div class="cv-hero-text"><div class="cv-kicker">Bước 3 · Sửa trên CVAT</div>'
            f'<h2 class="cv-title"><span class="cv-t-work">Đang làm trên CVAT</span><span class="cv-t-done">Mọi job đã xong</span></h2>'
            f'<div class="cv-sub"><span class="cv-t-work">Tự kiểm trạng thái job mỗi {INTERVAL} giây. Mọi job xong là tự chuyển sang <b>Gộp &amp; kết thúc</b>.</span>'
            '<span class="cv-t-done">Đã ngừng tự kiểm. Bấm <b>Merge jobs &amp; Finish</b> để gộp job và kết thúc đợt '
            '(có job bị mở lại trên CVAT thì bấm <b>Check now</b>).</span></div></div></div>')


def _run(store):
    return os.path.basename(os.path.normpath(store.run_dir))


def _kinds(ps):
    out = {}
    for j in (ps or {}).get("jobs") or []:
        if isinstance(j, dict) and isinstance(j.get("id"), int):
            out[j["id"]] = j.get("kind")
    return out


def _ann_jobs(kq):
    return [j for j in kq.get("jobs") or [] if j.get("type", "annotation") == "annotation"]


def _all_done(jobs):
    return bool(jobs) and all(j.get("state") == "completed" for j in jobs)


def poll(store, ctx, force=False, clock=time.monotonic, reopen=False):
    """Kiểm trạng thái job (tiến trình con cvat_jobs.py). reopen=True (nút Fix again khi mọi job đã xong): mở lại các job completed về in progress
    rồi đọc lại, trang quay về 'Đang làm trên CVAT' và tự kiểm tiếp."""
    if store is None:
        return None
    run = _run(store)
    ps = dot_anh.read_push(store.run_dir) or {}
    kq = ctx.cvat_jobs.setdefault(run, {})
    job = ctx.jobs_job
    snap = job.snapshot()
    if kq.get("pending") and snap["run"] == run and snap["state"] not in ("chua", "dang_chay"):
        r = nap_anh.read_jobs_result(snap["lines"], kq.get("task_id"))
        if not r["jobs"] and not r["loi"]:
            r["loi"] = day_cvat.last_message(snap["lines"]) or "Không đọc được trạng thái job."
        kq.update(pending=False, reopening=False, jobs=r["jobs"] if not r["loi"] else kq.get("jobs", []), loi=r["loi"],
                  at=datetime.datetime.now().strftime("%H:%M:%S"))
    if ps.get("trang_thai") != "xong" or dot_anh.read_gop(store.run_dir) or ctx.closing:
        return kq
    if kq.get("task_id") != ps.get("task_id"):
        kq.clear()
        kq["task_id"] = ps.get("task_id")
    reopen = reopen or bool(kq.get("reopen_next"))
    force = force or reopen
    if not force and _all_done(_ann_jobs(kq)):           # mọi job đã xong: ngừng tự kiểm (Check now vẫn kiểm lại được)
        return kq
    due = force or kq.get("started") is None or clock() - kq["started"] >= INTERVAL
    if not due or job.running or kq.get("pending") or not day_cvat.env_state()["ok"]:
        if reopen and day_cvat.env_state()["ok"]:
            kq["reopen_next"] = True                      # đang có lần kiểm dở: mở lại job ngay sau lần đó
        return kq
    kq.pop("reopen_next", None)
    try:
        if reopen:
            job.start(run, ctx.runs_root, ctx.project_root, reopen=True)
        else:
            job.start(run, ctx.runs_root, ctx.project_root)
    except RunError as e:
        kq.update(loi=str(e), started=clock())
        return kq
    kq.update(started=clock(), pending=True, reopening=reopen)     # đang mở lại: trang không báo 'mọi job đã xong' (không chạy lại cảnh kết, không tự sang Gộp)
    return kq


def model(store, ctx):
    if store is None:
        return dict(kind="none")
    run = _run(store)
    snap = ctx.push_job.snapshot()
    mine = snap["run"] == run
    if mine and snap["state"] == "dang_chay":
        return dict(kind="dang_day", run=run, snap=snap)
    ps = dot_anh.read_push(store.run_dir) or {}
    st = ps.get("trang_thai")
    url = dot_anh.safe_task_url(ps.get("task_url")) if st == "xong" else ""
    if st == "xong" and dot_anh.read_gop(store.run_dir):
        return dict(kind="da_gop", run=run, task=ps.get("task", ""), url=url)
    if st == "xong":
        kq = ctx.cvat_jobs.get(run) or {}
        if kq.get("task_id") != ps.get("task_id"):
            kq = {}
        kinds = _kinds(ps)
        jobs = [dict(j, kind=kinds.get(j["id"]) or j.get("kind")) for j in _ann_jobs(kq)]
        done = sum(1 for j in jobs if j.get("state") == "completed")
        env = day_cvat.env_state()
        reopening = bool(kq.get("reopening") or kq.get("reopen_next"))
        return dict(kind="theo_doi", run=run, task=ps.get("task", ""), task_id=ps.get("task_id"), url=url, jobs=jobs, done=done,
                    total=len(jobs), all_done=_all_done(jobs) and not reopening, reopening=reopening, loi=kq.get("loi"), at=kq.get("at"),
                    checking=bool(kq.get("pending")), env_ok=env["ok"], env_reason=env["reason"])
    if mine and snap["state"] in ("loi", "da_huy"):
        return dict(kind="loi_day", run=run, snap=snap, push=ps)
    if st in PARTIAL:
        return dict(kind="day_do", run=run, push=ps)
    return dict(kind="chua_day", run=run, remaining=store.progress()["remaining"])


BACK_BTN = '<button type="button" class="cv-btn" data-go="ra">Back to review</button>'


def _idle(title, body="", btn=BACK_BTN):
    return (f'<div class="cv-card cv-idle"><div class="cv-idle-title">{title}</div>'
            + (f'<div class="cv-idle-body">{body}</div>' if body else "") + f'<div class="cv-actions">{btn}</div></div>')


def _job_row(j):
    st = j.get("state", "")
    cls = "cv-st-ok" if st == "completed" else ("cv-st-bad" if st == "rejected" else ("cv-st-run" if st == "in progress" else "cv-st-new"))
    rng = f'frame {j["start"]}–{j["stop"]}' if j.get("start") is not None and j.get("stop") is not None else ""
    n = f'{j["n"]} ảnh' if j.get("n") is not None else ""
    kind = KIND_VI.get(j.get("kind"), "")
    meta = " · ".join(x for x in (kind, n, rng) if x)
    return (f'<div class="cv-job {cls}"><span class="cv-job-id">Job #{_e(j["id"])}</span><span class="cv-job-meta">{_e(meta)}</span>'
            f'<span class="cv-chip">{_e(STATE_VI.get(st, st or "?"))}</span><span class="cv-stage">{_e(j.get("stage", ""))}</span></div>')


def status_html(m):
    k = m["kind"]
    if k == "none":
        return _idle("Chưa có đợt nào đang mở.", "", '<button type="button" class="cv-btn" data-go="nap">New upload</button>')
    run = _e(m["run"])
    if k == "chua_day":
        left = m.get("remaining") or 0
        body = (f"Còn <b>{left}</b> mặt chưa rà." if left else "Đã rà hết: bấm <b>Push to CVAT</b> ở khung Duyệt &amp; Xuất CVAT.")
        btn = '<button type="button" class="cv-btn cv-btn-blue" data-go="push">Back to review</button>' if not left else BACK_BTN
        return _idle(f"Đợt <b>{run}</b> chưa đẩy lên CVAT.", body, btn)
    if k == "dang_day":
        return (f'<div class="cv-card cv-pushing"><div class="cv-line">Đang tạo task và nhập nhãn nháp của đợt <b>{run}</b> lên CVAT…</div>'
                f'{day_cvat.progress_html(m["snap"])}</div>')
    if k == "loi_day":
        snap = m["snap"]
        body = (day_cvat.error_html(snap, m["push"], m["run"]) if snap["state"] == "loi" else day_cvat.cancelled_html(m["push"], m["run"]))
        return f'<div class="cv-card cv-idle">{body}<div class="cv-actions">{BACK_BTN}</div></div>'
    if k == "day_do":
        return _idle(f"Lần đẩy đợt <b>{run}</b> dừng giữa chừng.", _e(day_cvat.next_step(m["push"], m["run"])))
    open_btn = (f'<a class="cv-btn cv-btn-blue" href="{_e(m["url"])}" target="_blank" rel="noopener noreferrer">Open CVAT task ↗</a>'
                if m.get("url") else "")
    if k == "da_gop":
        return _idle(f"Đợt <b>{run}</b> đã gộp job xong.", f'Task <b>{_e(m["task"])}</b>.',
                     '<button type="button" class="cv-btn" data-go="gop">View result</button>' + open_btn)
    total, done = m["total"], m["done"]
    pct = round(100 * done / total) if total else 0
    if not m["env_ok"]:
        state = (f'<span class="cv-warn-txt">Chưa kết nối CVAT ({_e(m["env_reason"] or "")}): không tự kiểm được.</span>'
                 '<button type="button" class="cv-btn" data-cd-open="cvat">Set CVAT</button>')
    elif m.get("reopening"):
        state = '<span class="cv-at cv-spin">Đang mở lại job trên CVAT…</span>'
    elif m["checking"]:
        state = '<span class="cv-at cv-spin">Đang kiểm…</span>'
    else:
        stop = " · đã ngừng tự kiểm" if m["all_done"] else ""
        state = f'<span class="cv-at">Kiểm lúc {_e(m["at"])}{stop}</span>' if m.get("at") else '<span class="cv-at">Chưa kiểm</span>'
    check = ""
    if m["env_ok"]:                                         # mọi job xong: Check now thành Fix again (mở lại job trên CVAT để sửa tiếp)
        check = ('<button type="button" class="cv-btn" data-cv-reopen title="Sửa lại: mở lại các job trên CVAT (Xong → Đang sửa) để sửa tiếp">Fix again</button>'
                 if m["all_done"] else '<button type="button" class="cv-btn" data-cv-check>Check now</button>')
    count = (f'<div class="cv-count"><b>{done}</b><span>/{total} job đã xong</span></div>' if total else
             '<div class="cv-count"><span>Chưa có số job</span></div>')
    rows = "".join(_job_row(j) for j in m["jobs"])
    loi = f'<div class="m28-warn cv-loi">{_e(m["loi"])}</div>' if m.get("loi") else ""
    done_box = ""
    key = f'{m["run"]}:{m["task_id"]}'
    if m["all_done"]:
        done_box = (f'<div class="cv-all-done" data-run="{run}" data-key="{_e(key)}"><b>Mọi job đã xong.</b> Bấm Merge jobs &amp; Finish để gộp job và kết thúc đợt.'
                    f'<button type="button" class="cv-btn cv-btn-green" data-cv-finish data-run="{run}">Merge jobs &amp; Finish</button></div>')
    is_open = bool(total) and not m["all_done"] and not m.get("reopening")     # job thật sự đang sửa: JS xoá dấu 'đã xem cảnh kết', xong lần nữa thì chạy lại
    return (f'<div class="cv-card cv-watch" data-key="{_e(key)}" data-open="{int(is_open)}"><div class="cv-top"><div class="cv-task"><span class="cv-task-name">{_e(m["task"])}</span>'
            f'<span class="cv-task-run">đợt {run}</span></div>{count}<div class="cv-actions">{check}{open_btn}</div></div>'
            f'<div class="m28-bar cv-bar" role="progressbar" aria-valuenow="{done}" aria-valuemax="{total}"><i style="width:{pct}%"></i></div>'
            f'<div class="cv-state">{state}</div>{loi}{done_box}<div class="cv-jobs">{rows}</div></div>')


def cvat_tab(gr, demo, store, ctx):
    gr.HTML(hero_html(asset_uri()), elem_id="cv-hero", apply_default_css=False)
    status = gr.HTML(elem_id="cv-status", apply_default_css=False)
    b_check = gr.Button(visible="hidden", elem_id="cv-check-go")
    b_reopen = gr.Button(visible="hidden", elem_id="cv-reopen-go")
    timer = gr.Timer(5.0)
    outs = [status]
    opts = dict(show_progress="hidden", api_visibility="private", concurrency_limit=1, concurrency_id="cv")

    def refresh():
        poll(store, ctx)
        return status_html(model(store, ctx))

    def on_check():
        poll(store, ctx, force=True)
        return status_html(model(store, ctx))

    def on_reopen():
        poll(store, ctx, force=True, reopen=True)
        return status_html(model(store, ctx))

    timer.tick(refresh, None, outs, **opts)
    b_check.click(on_check, None, outs, **opts)
    b_reopen.click(on_reopen, None, outs, **opts)
    demo.load(refresh, None, outs, **opts)
    return refresh, outs, opts


CSS = """
#tab-cvat { max-width: 1100px; margin: 0 auto; width: 100%; gap: 12px; padding-top: 4px !important; }
#cv-hero .html-container, #cv-status .html-container { padding: 0 !important; }
#tab-cvat:has(.cv-idle) #cv-hero { display: none; }
.cv-hero { display: flex; align-items: center; gap: 18px 28px; flex-wrap: wrap; padding: 18px 22px; border-radius: 18px; overflow: hidden;
  background: radial-gradient(120% 140% at 0% 0%, #10284d 0%, #0a0f1d 55%, #060913 100%); border: 1px solid #1e2b42; }
.cv-art { position: relative; flex: 1 1 460px; max-width: 640px; aspect-ratio: 2 / 1; border-radius: 14px; overflow: hidden;
  box-shadow: 0 14px 36px rgba(0, 0, 0, .45), 0 0 0 1px rgba(56, 189, 248, .15); }
.cv-svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
.cv-hero-text { flex: 1 1 240px; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.cv-kicker { font-size: 13px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; color: #7dd3fc; }
.cv-title { margin: 0 !important; font-size: 32px; line-height: 1.15; font-weight: 800; color: #f1f5f9;
  background: linear-gradient(90deg, #e0f2fe, #7dd3fc 45%, #22d3ee); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.cv-sub { font-size: 14px; color: #94a3b8; line-height: 1.5; }
.cv-sub b { color: #e2e8f0; }
.cv-t-done { display: none; }
#tab-cvat:has(.cv-all-done) .cv-t-work { display: none; }
#tab-cvat:has(.cv-all-done) .cv-t-done { display: inline; }
.cv-stars circle { animation: cv-twinkle 2.4s ease-in-out infinite alternate; }
.cv-stars circle:nth-child(2n) { animation-delay: -1.2s; } .cv-stars circle:nth-child(3n) { animation-duration: 3.2s; }
.cv-petal { opacity: 0; animation: cv-petal 8s linear infinite; }
.cv-ys { animation: cv-lunge 4.8s ease-in-out infinite, cv-vanish 4.8s linear infinite; }
.cv-upper { transform-origin: 130px 136px; animation: cv-lean 4.8s ease-in-out infinite; }
.cv-rear { transform-origin: 124px 98px; animation: cv-rear 4.8s ease-in-out infinite; }
.cv-tail { transform-origin: 124px 66px; animation: cv-flap .8s ease-in-out infinite alternate; }
.cv-scarf { transform-origin: 132px 92px; animation: cv-flap .65s ease-in-out infinite alternate-reverse; }
.cv-sash { transform-origin: 116px 134px; animation: cv-flap .7s ease-in-out infinite alternate; }
.cv-arm { transform-origin: 144px 95px; animation: cv-shoulder 4.8s linear infinite; }
.cv-fore { transform-origin: 162px 111px; animation: cv-elbow 4.8s linear infinite; }
.cv-hand { transform-origin: 186px 104px; animation: cv-wrist 4.8s linear infinite; }
.cv-q3glow { opacity: 0; animation: cv-q3 4.8s ease-in-out infinite; }
.cv-glint { opacity: 0; animation: cv-glint 4.8s linear infinite; }
.cv-spark { opacity: 0; transform-origin: 366px 104.5px; animation: cv-spark 4.8s ease-out infinite; }
.cv-dummy { transform-origin: 380px 208px; animation: cv-dummy 4.8s ease-in-out infinite; }
.cv-dm-flash { opacity: 0; animation: cv-flash 4.8s linear infinite; }
.cv-dm-shadow { transform-origin: 380px 210px; animation: cv-shadow 4.8s ease-in-out infinite; }
.cv-tor { opacity: 0; transform-origin: 300px 205px; animation: cv-tor 4.8s ease-in-out infinite; }
.cv-ring { fill: none; stroke: #bae6fd; stroke-width: 2.6; stroke-linecap: round; stroke-dasharray: 52 18; transform-box: fill-box; transform-origin: center;
  animation: cv-spin .7s linear infinite; }
.cv-ring:nth-child(2n) { stroke: #7dd3fc; animation-delay: -.12s; } .cv-ring:nth-child(3n) { stroke: #e0f2fe; animation-delay: -.25s; }
.cv-ring:nth-child(4n) { animation-delay: -.37s; } .cv-ring:nth-child(5n) { animation-delay: -.5s; }
.cv-swirl { transform-origin: 300px 120px; animation: cv-sway .5s ease-in-out infinite alternate; }
.cv-dust { opacity: 0; fill: #94a3b8; transform-origin: 380px 206px; animation: cv-dust 4.8s ease-out infinite; }
.cv-swf { animation: cv-swf 4.8s linear infinite; }
.cv-swb { animation: cv-swb 4.8s linear infinite; }
.cv-blade { transform-origin: 195px 104.5px; animation: cv-draw 4.8s linear infinite; }
.cv-drawflash { opacity: 0; animation: cv-drawflash 4.8s ease-out infinite; }
.cv-mouth { opacity: 0; transform-origin: 110.0px 114.8px; animation: cv-mouth 4.8s ease-out infinite; }
.cv-blink { opacity: 0; transform-origin: 146px 124px; animation: cv-blink 4.8s ease-out infinite; }
.cv-dash { opacity: 0; transform-origin: 176px 116px; animation: cv-dash 4.8s ease-out infinite; }
.cv-rfollow { animation: cv-rfollow 4.8s ease-in-out infinite; }
.cv-rsl { opacity: 0; transform-origin: 0 0; rotate: var(--r, 0deg); translate: var(--x, 0px) var(--y, 0px); animation: cv-rsl 4.8s ease-out infinite; }
.cv-rx { opacity: 0; transform-origin: 0 0; animation: cv-rx 4.8s ease-out infinite; }
@keyframes cv-draw { 0%, 5% { transform: scaleX(.001); animation-timing-function: ease-out; } 7.4%, 19.3% { transform: scaleX(1); animation-timing-function: ease-in; }
  21.5%, 27% { transform: scaleX(.001); animation-timing-function: ease-out; } 29.4%, 66% { transform: scaleX(1); } 67%, 100% { transform: scaleX(.001); } }
@keyframes cv-swf { 0%, 7.39% { opacity: 0; } 7.4%, 19.29% { opacity: 1; } 19.3%, 29.39% { opacity: 0; } 29.4%, 76% { opacity: 1; } 76.1%, 100% { opacity: 0; } }
@keyframes cv-swb { 0%, 7.39% { opacity: 1; } 7.4%, 19.29% { opacity: 0; } 19.3%, 29.39% { opacity: 1; } 29.4%, 76% { opacity: 0; } 76.1%, 100% { opacity: 1; } }
@keyframes cv-drawflash { 0%, 5.5% { opacity: 0; } 6.6% { opacity: 1; } 8.2% { opacity: 0; } 27.5% { opacity: 0; } 28.6% { opacity: 1; } 30.2%, 100% { opacity: 0; } }
@keyframes cv-mouth { 0%, 5% { opacity: 0; transform: scale(.3); } 6% { opacity: 1; transform: scale(1); } 8% { opacity: 0; transform: scale(1.6); }
  20% { opacity: 0; transform: scale(.3); } 21% { opacity: 1; transform: scale(1); } 23% { opacity: 0; transform: scale(1.6); }
  27% { opacity: 0; transform: scale(.3); } 28% { opacity: 1; transform: scale(1); } 30%, 100% { opacity: 0; transform: scale(1.7); } }
@keyframes cv-vanish { 0%, 64% { opacity: 1; } 65.5% { opacity: 0; } 86% { opacity: 0; } 88.5%, 100% { opacity: 1; } }
@keyframes cv-blink { 0%, 64% { opacity: 0; transform: scale(.3); } 65% { opacity: 1; transform: scale(.85); } 69% { opacity: 0; transform: scale(1.7); }
  70%, 86% { opacity: 0; transform: scale(.3); } 87% { opacity: 1; transform: scale(.85); } 91%, 100% { opacity: 0; transform: scale(1.6); } }
@keyframes cv-dash { 0%, 64.5% { opacity: 0; transform: scaleX(0); } 65.5% { opacity: 1; transform: scaleX(1); } 68%, 100% { opacity: 0; transform: scaleX(1.04); } }
@keyframes cv-rfollow { 0%, 62.5% { transform: translateY(0); } 65% { transform: translateY(-20px); } 69% { transform: translateY(-36px); }
  74% { transform: translateY(-40px); } 79% { transform: translateY(-20px); } 83%, 100% { transform: translateY(0); } }
@keyframes cv-rsl { 0%, 69.6% { opacity: 0; scale: .3; } 70.4% { opacity: 1; scale: 1; } 72.5% { opacity: 1; scale: 1.06; } 75.5%, 100% { opacity: 0; scale: 1.2; } }
@keyframes cv-rx { 0%, 78.4% { opacity: 0; scale: .35; } 79.2% { opacity: 1; scale: 1; } 82.5%, 100% { opacity: 0; scale: 1.25; } }
.cv-cut { opacity: 0; transform-origin: -50px 0; }
.cv-cut1 { animation: cv-cut1 4.8s ease-out infinite; }
.cv-cut2 { animation: cv-cut2 4.8s ease-out infinite; }
.cv-tag { font: 800 12px/1 system-ui, sans-serif; letter-spacing: 1.5px; fill: #fef3c7; stroke: #1f1305; stroke-width: 3px; paint-order: stroke; }
@keyframes cv-cut1 { 0%, 11.8% { opacity: 0; transform: scaleX(0); } 12.5% { opacity: 1; transform: scaleX(1); } 14.5% { opacity: .9; transform: scaleX(1); } 17.5%, 100% { opacity: 0; transform: scaleX(1); } }
@keyframes cv-cut2 { 0%, 33.8% { opacity: 0; transform: scaleX(0); } 34.5% { opacity: 1; transform: scaleX(1); } 36.5% { opacity: .9; transform: scaleX(1); } 39.5%, 100% { opacity: 0; transform: scaleX(1); } }
.cv-dark, .cv-half, .cv-ecut { opacity: 0; }
.cv-finale .cv-dummy, .cv-finale .cv-dm-shadow, .cv-finale .cv-tor, .cv-finale .cv-rfollow, .cv-finale .cv-blink, .cv-finale .cv-dash, .cv-finale .cv-spark,
.cv-finale .cv-dust, .cv-finale .cv-petal, .cv-finale .cv-q3glow, .cv-finale .cv-glint, .cv-finale .cv-drawflash { display: none; }
.cv-finale .cv-arm, .cv-finale .cv-fore, .cv-finale .cv-hand, .cv-finale .cv-blade, .cv-finale .cv-swf, .cv-finale .cv-swb, .cv-finale .cv-upper,
.cv-finale .cv-rear { animation: none; }
.cv-finale .cv-arm { transform: rotate(14deg); }
.cv-finale .cv-fore { transform: rotate(-30deg) scaleX(-1); }
.cv-finale .cv-hand { transform: rotate(-16deg); }
.cv-finale .cv-blade { transform: scaleX(.001); }
.cv-finale .cv-swf { opacity: 0; }
.cv-finale .cv-swb { opacity: 1; }
.cv-finale .cv-mouth { animation: cv-fmouth 3400ms ease-out forwards; }
@keyframes cv-fmouth { 0%, 52% { opacity: 0; transform: scale(.3); } 54% { opacity: 1; transform: scale(1.2); } 60%, 100% { opacity: 0; transform: scale(1.8); } }
.cv-finale .cv-dark { animation: cv-fdark 3400ms ease-out forwards; }
.cv-finale .cv-ys { animation: cv-edash 3400ms linear forwards; }
.cv-finale .cv-half { opacity: 1; }
.cv-finale .cv-fdummy { animation: cv-fslide 3400ms ease-in-out forwards; }
.cv-finale .cv-half-top { transform-origin: 380px 100px; animation: cv-ftop 3400ms ease-in forwards; }
.cv-finale .cv-half-bot { transform-origin: 380px 208px; animation: cv-fbot 3400ms ease-out forwards; }
.cv-finale .cv-ecut { transform-origin: 0 0; animation: cv-fcut 3400ms ease-out forwards; }
.cv-finale.cv-fin-end .cv-mouth, .cv-finale.cv-fin-end .cv-dark, .cv-finale.cv-fin-end .cv-ys, .cv-finale.cv-fin-end .cv-fdummy,
.cv-finale.cv-fin-end .cv-half-top, .cv-finale.cv-fin-end .cv-half-bot, .cv-finale.cv-fin-end .cv-ecut { animation-delay: -3400ms; }
@keyframes cv-fdark { 0% { opacity: 0; } 12%, 100% { opacity: 1; } }
@keyframes cv-fslide { 0% { transform: translateX(0); opacity: 1; } 12% { transform: translateX(0); opacity: 0; } 12.1%, 18% { transform: translateX(-140px); opacity: 0; }
  30%, 100% { transform: translateX(-140px); opacity: 1; } }
@keyframes cv-edash { 0%, 6% { transform: translateX(0); opacity: 1; } 14% { transform: translateX(0); opacity: 0; }
  14.1%, 36% { transform: translateX(-70px); opacity: 0; } 42% { transform: translateX(-70px); opacity: 1; } 47% { transform: translateX(-78px); opacity: 1;
  animation-timing-function: cubic-bezier(.6, 0, .9, .4); } 55% { transform: translateX(230px); opacity: .6; } 62%, 100% { transform: translateX(440px); opacity: 0; } }
@keyframes cv-fcut { 0%, 63% { opacity: 0; transform: scaleX(0); } 65.5% { opacity: 1; transform: scaleX(1); } 76% { opacity: .9; transform: scaleX(1); } 88%, 100% { opacity: 0; transform: scaleX(1); } }
@keyframes cv-ftop { 0%, 67% { transform: translate(0, 0) rotate(0deg); } 73% { transform: translate(12px, -7px) rotate(-6deg); } 84% { transform: translate(30px, 40px) rotate(18deg); }
  93% { transform: translate(38px, 88px) rotate(38deg); } 97% { transform: translate(40px, 82px) rotate(36deg); } 100% { transform: translate(41px, 88px) rotate(38deg); } }
@keyframes cv-fbot { 0%, 66% { transform: rotate(0deg); } 71% { transform: rotate(3deg); } 77% { transform: rotate(-1.5deg); } 83%, 100% { transform: rotate(0deg); } }
@keyframes cv-twinkle { from { opacity: .25; } to { opacity: 1; } }
@keyframes cv-petal { 0% { opacity: 0; transform: translate(var(--x0), var(--y0)) rotate(0deg); } 8% { opacity: .9; } 90% { opacity: .9; }
  100% { opacity: 0; transform: translate(var(--x1), var(--y1)) rotate(620deg); } }
@keyframes cv-flap { from { transform: rotate(-4deg) skewX(-5deg); } to { transform: rotate(4deg) skewX(5deg); } }
@keyframes cv-lunge {
  0% { transform: translateX(0); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  5% { transform: translateX(0); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  7% { transform: translateX(-4px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  11.5% { transform: translateX(12px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  16% { transform: translateX(12px); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  22% { transform: translateX(0); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  27% { transform: translateX(0); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  29% { transform: translateX(-3px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  33.5% { transform: translateX(12px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  39% { transform: translateX(12px); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  41.5% { transform: translateX(6px); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  45% { transform: translateX(10px); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  48.5% { transform: translateX(5px); animation-timing-function: cubic-bezier(.3, .1, .3, 1); }
  52% { transform: translateX(-7px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  57.5% { transform: translateX(18px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  64% { transform: translateX(18px); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  80% { transform: translateX(0); }
  100% { transform: translateX(0); }
}
@keyframes cv-shoulder {
  0% { transform: rotate(14deg); animation-timing-function: ease-in-out; }
  5% { transform: rotate(14deg); animation-timing-function: ease-in; }
  7.4% { transform: rotate(14deg); animation-timing-function: ease-out; }
  8.8% { transform: rotate(14deg); animation-timing-function: ease-in; }
  12% { transform: rotate(-40deg); animation-timing-function: ease-out; }
  14% { transform: rotate(-38deg); animation-timing-function: ease-in-out; }
  16% { transform: rotate(-38deg); animation-timing-function: ease-in-out; }
  17.5% { transform: rotate(14deg); animation-timing-function: ease-in; }
  19.3% { transform: rotate(14deg); animation-timing-function: ease-out; }
  21.5% { transform: rotate(14deg); animation-timing-function: ease-in-out; }
  27% { transform: rotate(14deg); animation-timing-function: ease-in; }
  29.4% { transform: rotate(14deg); animation-timing-function: ease-out; }
  30.8% { transform: rotate(14deg); animation-timing-function: ease-in; }
  34% { transform: rotate(-34deg); animation-timing-function: ease-out; }
  36% { transform: rotate(-32deg); animation-timing-function: ease-in-out; }
  39% { transform: rotate(-32deg); animation-timing-function: ease-in-out; }
  42% { transform: rotate(-20deg); animation-timing-function: ease-in-out; }
  45% { transform: rotate(-8deg); animation-timing-function: ease-in-out; }
  48.5% { transform: rotate(-22deg); animation-timing-function: ease-in-out; }
  51% { transform: rotate(-4deg); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  54.5% { transform: rotate(96deg); animation-timing-function: ease-in; }
  58% { transform: rotate(-42deg); animation-timing-function: ease-out; }
  60.5% { transform: rotate(-40deg); animation-timing-function: ease-in-out; }
  64.5% { transform: rotate(-40deg); animation-timing-function: ease-in-out; }
  76% { transform: rotate(14deg); animation-timing-function: ease-in-out; }
  100% { transform: rotate(14deg); }
}
@keyframes cv-elbow {
  0% { transform: rotate(-30deg) scaleX(-1); animation-timing-function: ease-in-out; }
  5% { transform: rotate(-30deg) scaleX(-1); animation-timing-function: ease-in; }
  7.4% { transform: rotate(-14deg) scaleX(0); animation-timing-function: ease-out; }
  8.8% { transform: rotate(2deg) scaleX(1); animation-timing-function: ease-in; }
  12% { transform: rotate(58deg) scaleX(1); animation-timing-function: ease-out; }
  14% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  16% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  17.5% { transform: rotate(2deg) scaleX(1); animation-timing-function: ease-in; }
  19.3% { transform: rotate(-14deg) scaleX(0); animation-timing-function: ease-out; }
  21.5% { transform: rotate(-30deg) scaleX(-1); animation-timing-function: ease-in-out; }
  27% { transform: rotate(-30deg) scaleX(-1); animation-timing-function: ease-in; }
  29.4% { transform: rotate(-14deg) scaleX(0); animation-timing-function: ease-out; }
  30.8% { transform: rotate(2deg) scaleX(1); animation-timing-function: ease-in; }
  34% { transform: rotate(58deg) scaleX(1); animation-timing-function: ease-out; }
  36% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  39% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  42% { transform: rotate(30deg) scaleX(1); animation-timing-function: ease-in-out; }
  45% { transform: rotate(20deg) scaleX(1); animation-timing-function: ease-in-out; }
  48.5% { transform: rotate(34deg) scaleX(1); animation-timing-function: ease-in-out; }
  51% { transform: rotate(22deg) scaleX(1); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  54.5% { transform: rotate(-108deg) scaleX(1); animation-timing-function: ease-in; }
  58% { transform: rotate(58deg) scaleX(1); animation-timing-function: ease-out; }
  60.5% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  64.5% { transform: rotate(57deg) scaleX(1); animation-timing-function: ease-in-out; }
  76% { transform: rotate(-30deg) scaleX(-1); animation-timing-function: ease-in-out; }
  100% { transform: rotate(-30deg) scaleX(-1); }
}
@keyframes cv-wrist {
  0% { transform: rotate(-16deg); animation-timing-function: ease-in-out; }
  5% { transform: rotate(-16deg); animation-timing-function: ease-in; }
  7.4% { transform: rotate(-16deg); animation-timing-function: ease-out; }
  8.8% { transform: rotate(-16deg); animation-timing-function: ease-in; }
  12% { transform: rotate(-20deg); animation-timing-function: ease-out; }
  14% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  16% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  17.5% { transform: rotate(-16deg); animation-timing-function: ease-in; }
  19.3% { transform: rotate(-16deg); animation-timing-function: ease-out; }
  21.5% { transform: rotate(-16deg); animation-timing-function: ease-in-out; }
  27% { transform: rotate(-16deg); animation-timing-function: ease-in; }
  29.4% { transform: rotate(-16deg); animation-timing-function: ease-out; }
  30.8% { transform: rotate(-16deg); animation-timing-function: ease-in; }
  34% { transform: rotate(-20deg); animation-timing-function: ease-out; }
  36% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  39% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  42% { transform: rotate(-72deg); animation-timing-function: ease-in-out; }
  45% { transform: rotate(50deg); animation-timing-function: ease-in-out; }
  48.5% { transform: rotate(-60deg); animation-timing-function: ease-in-out; }
  51% { transform: rotate(10deg); animation-timing-function: cubic-bezier(.45, 0, .25, 1); }
  54.5% { transform: rotate(22deg); animation-timing-function: ease-in; }
  58% { transform: rotate(-20deg); animation-timing-function: ease-out; }
  60.5% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  64.5% { transform: rotate(-19deg); animation-timing-function: ease-in-out; }
  76% { transform: rotate(-16deg); animation-timing-function: ease-in-out; }
  100% { transform: rotate(-16deg); }
}
@keyframes cv-lean {
  0% { transform: rotate(0deg); }
  5% { transform: rotate(-3deg); }
  8.8% { transform: rotate(2deg); }
  12% { transform: rotate(7deg); }
  14% { transform: rotate(8deg); }
  16% { transform: rotate(7deg); }
  21.5% { transform: rotate(0deg); }
  27% { transform: rotate(-3deg); }
  30.8% { transform: rotate(2deg); }
  34% { transform: rotate(7deg); }
  36% { transform: rotate(8deg); }
  39% { transform: rotate(6deg); }
  42% { transform: rotate(2deg); }
  45% { transform: rotate(5deg); }
  48.5% { transform: rotate(1deg); }
  54.5% { transform: rotate(-5deg); }
  58% { transform: rotate(9deg); }
  61% { transform: rotate(9deg); }
  76% { transform: rotate(0deg); }
  100% { transform: rotate(0deg); }
}
@keyframes cv-rear {
  0% { transform: rotate(0deg); }
  5% { transform: rotate(-3deg); }
  8.8% { transform: rotate(4deg); }
  12% { transform: rotate(22deg); }
  14% { transform: rotate(26deg); }
  16% { transform: rotate(22deg); }
  21.5% { transform: rotate(0deg); }
  27% { transform: rotate(-3deg); }
  30.8% { transform: rotate(4deg); }
  34% { transform: rotate(22deg); }
  36% { transform: rotate(26deg); }
  39% { transform: rotate(20deg); }
  42% { transform: rotate(8deg); }
  45% { transform: rotate(-6deg); }
  48.5% { transform: rotate(10deg); }
  54.5% { transform: rotate(-14deg); }
  58% { transform: rotate(28deg); }
  61% { transform: rotate(28deg); }
  76% { transform: rotate(0deg); }
  100% { transform: rotate(0deg); }
}
@keyframes cv-q3 { 0%, 38% { opacity: 0; } 43%, 57% { opacity: .55; } 62%, 100% { opacity: 0; } }
@keyframes cv-glint { 0%, 10% { opacity: 0; transform: translateX(0); } 11% { opacity: 1; } 14% { opacity: 0; transform: translateX(78px); }
  32% { opacity: 0; transform: translateX(0); } 33% { opacity: 1; } 36% { opacity: 0; transform: translateX(78px); }
  40.5% { opacity: 0; transform: translateX(0); } 41.5% { opacity: 1; } 43.5% { opacity: 0; transform: translateX(78px); }
  44% { opacity: 0; transform: translateX(0); } 45% { opacity: 1; } 47% { opacity: 0; transform: translateX(78px); }
  47.6% { opacity: 0; transform: translateX(0); } 48.5% { opacity: 1; } 50.5% { opacity: 0; transform: translateX(78px); }
  56% { opacity: 0; transform: translateX(0); } 57% { opacity: 1; } 60%, 100% { opacity: 0; transform: translateX(78px); } }
@keyframes cv-spark { 0%, 12% { opacity: 0; transform: scale(.2); } 13% { opacity: 1; transform: scale(.7); } 17% { opacity: 0; transform: scale(1.4); }
  34% { opacity: 0; transform: scale(.2); } 35% { opacity: 1; transform: scale(.7); } 39% { opacity: 0; transform: scale(1.4); }
  63% { opacity: 0; transform: scale(.3); } 64.5% { opacity: 1; transform: scale(1.1); } 70%, 100% { opacity: 0; transform: scale(2); } }
@keyframes cv-dummy {
  0%, 12.5% { transform: translateY(0) rotate(0deg) scale(1, 1); } 13.5% { transform: translateY(0) rotate(10deg) scale(1, 1); }
  15% { transform: translateY(0) rotate(-6deg) scale(1, 1); } 16.5% { transform: translateY(0) rotate(3.5deg) scale(1, 1); }
  18% { transform: translateY(0) rotate(-1.5deg) scale(1, 1); } 19.5%, 34.5% { transform: translateY(0) rotate(0deg) scale(1, 1); }
  35.5% { transform: translateY(0) rotate(10deg) scale(1, 1); } 37% { transform: translateY(0) rotate(-6deg) scale(1, 1); }
  38.5% { transform: translateY(0) rotate(3.5deg) scale(1, 1); } 40% { transform: translateY(0) rotate(-1.5deg) scale(1, 1); }
  41.5%, 62.5% { transform: translateY(0) rotate(0deg) scale(1, 1); } 65% { transform: translateY(-20px) rotate(-10deg) scale(1, 1); }
  69% { transform: translateY(-36px) rotate(14deg) scale(1, 1); } 74% { transform: translateY(-40px) rotate(-10deg) scale(1, 1); }
  79% { transform: translateY(-20px) rotate(6deg) scale(1, 1); } 83% { transform: translateY(0) rotate(0deg) scale(1, 1); }
  85% { transform: translateY(0) rotate(0deg) scale(1.07, .9); } 88% { transform: translateY(0) rotate(0deg) scale(.97, 1.04); }
  91%, 100% { transform: translateY(0) rotate(0deg) scale(1, 1); } }
@keyframes cv-flash { 0%, 12.8% { opacity: 0; } 13.4% { opacity: .75; } 15.5% { opacity: 0; } 35% { opacity: 0; } 35.6% { opacity: .75; } 37.6% { opacity: 0; }
  64% { opacity: 0; } 64.8% { opacity: .85; } 67.5% { opacity: 0; } 70.4% { opacity: 0; } 70.9% { opacity: .55; } 72% { opacity: 0; }
  72.5% { opacity: 0; } 73% { opacity: .55; } 74.1% { opacity: 0; } 74.6% { opacity: 0; } 75.1% { opacity: .55; } 76.2% { opacity: 0; }
  76.6% { opacity: 0; } 77.1% { opacity: .55; } 78.2% { opacity: 0; } 78.8% { opacity: 0; } 79.3% { opacity: .9; } 81.5%, 100% { opacity: 0; } }
@keyframes cv-shadow { 0%, 63% { transform: scale(1); opacity: .5; } 69%, 76% { transform: scale(.45); opacity: .2; } 83%, 100% { transform: scale(1); opacity: .5; } }
@keyframes cv-tor {
  0%, 55% { opacity: 0; transform: translateX(0) scale(.2); animation-timing-function: linear; }
  58% { opacity: 1; transform: translateX(6px) scale(.6); animation-timing-function: linear; }
  60.5% { opacity: 1; transform: translateX(38px) scale(.95); animation-timing-function: linear; }
  63% { opacity: 1; transform: translateX(72px) scale(1.22); animation-timing-function: linear; }
  66% { opacity: 1; transform: translateX(94px) scale(1.4); animation-timing-function: linear; }
  70% { opacity: 1; transform: translateX(114px) scale(1.52); animation-timing-function: linear; }
  74% { opacity: .85; transform: translateX(136px) scale(1.58); animation-timing-function: linear; }
  78%, 100% { opacity: 0; transform: translateX(164px) scale(1.62); } }
@keyframes cv-spin { 0% { transform: translateX(-4px) scaleX(1); stroke-dashoffset: 0; } 50% { transform: translateX(4px) scaleX(.86); }
  100% { transform: translateX(-4px) scaleX(1); stroke-dashoffset: -70; } }
@keyframes cv-sway { from { transform: rotate(-8deg); } to { transform: rotate(8deg); } }
@keyframes cv-dust { 0%, 82.5% { opacity: 0; transform: scale(.3); } 84.5% { opacity: .6; transform: scale(1); } 93%, 100% { opacity: 0; transform: scale(1.7); } }
@media (prefers-reduced-motion: reduce) {
  .cv-hero *, .cv-hero *::before { animation: none !important; }
  .cv-cut, .cv-spark, .cv-tor, .cv-dust, .cv-petal, .cv-dm-flash, .cv-q3glow, .cv-glint, .cv-blink, .cv-dash, .cv-rsl, .cv-rx, .cv-drawflash, .cv-mouth, .cv-swb, .cv-dark, .cv-half, .cv-ecut { opacity: 0 !important; }
}
.cv-card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border-radius: 16px; background: #0a0f1d; border: 1px solid #1e2b42; }
.cv-top { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 18px; }
.cv-task { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cv-task-name { font-family: var(--font-mono); font-size: 15px; font-weight: 800; color: #f1f5f9; overflow-wrap: anywhere; }
.cv-task-run { font-size: 13px; color: #94a3b8; }
.cv-count { display: flex; align-items: baseline; gap: 2px; font-size: 14px; color: #94a3b8; }
.cv-count b { font-size: 26px; color: #f1f5f9; }
.cv-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; }
.cv-idle .cv-actions { margin-left: 0; }
.cv-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 0 14px; border-radius: 10px; cursor: pointer;
  font-size: 14px; font-weight: 700; color: #e2e8f0 !important; text-decoration: none !important; background: #0e1626; border: 1px solid #1e2b42; }
.cv-btn:hover { background: #152238; }
.cv-btn:focus-visible { outline: 3px solid #3b82f6; outline-offset: 2px; }
.cv-btn-blue { background: linear-gradient(135deg, #2563eb, #1d4ed8); border-color: #1d4ed8; color: #fff !important; }
.cv-btn-green { background: linear-gradient(90deg, #059669, #0d9488); border-color: #0f766e; color: #fff !important; }
.cv-bar { flex: none !important; width: 100%; height: 8px !important; background: #060913; border: 1px solid #1e2b42; }
.cv-bar > i { background: linear-gradient(90deg, #10b981, #22d3ee) !important; }
.cv-state { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 13px; color: #94a3b8; }
.cv-spin::before { content: ""; display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 50%; border: 2px solid #38bdf8;
  border-right-color: transparent; vertical-align: -1px; animation: cv-rot .8s linear infinite; }
@keyframes cv-rot { to { transform: rotate(360deg); } }
.cv-warn-txt { color: #fbbf24; }
.cv-all-done { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 10px 12px; border-radius: 12px; font-size: 14px; color: #d1fae5;
  background: rgba(16, 185, 129, .12); border: 1px solid rgba(16, 185, 129, .45); }
.cv-all-done .cv-btn { margin-left: auto; }
.cv-jobs { display: flex; flex-direction: column; gap: 6px; }
.cv-job { display: grid; grid-template-columns: 90px 1fr auto auto; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 10px;
  background: #0e1626; border: 1px solid #1e2b42; border-left: 4px solid var(--jc, #64748b); font-size: 13px; }
.cv-job-id { font-family: var(--font-mono); font-weight: 800; color: #f1f5f9; }
.cv-job-meta { color: #94a3b8; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cv-chip { padding: 2px 10px; border-radius: 999px; font-weight: 700; font-size: 13px; color: var(--jc, #94a3b8);
  background: color-mix(in srgb, var(--jc, #64748b) 16%, transparent); border: 1px solid color-mix(in srgb, var(--jc, #64748b) 45%, transparent); }
.cv-stage { font-size: 13px; color: #64748b; min-width: 70px; text-align: right; }
.cv-st-ok { --jc: #10b981; } .cv-st-run { --jc: #38bdf8; } .cv-st-bad { --jc: #f43f5e; } .cv-st-new { --jc: #94a3b8; }
.cv-idle { align-items: flex-start; }
.cv-idle-title { font-size: 16px; font-weight: 800; color: #f1f5f9; }
.cv-idle-body { font-size: 14px; color: #cbd5e1; }
.cv-pushing .cv-line { font-size: 15px; color: #e2e8f0; }
@media (max-width: 640px) { .cv-job { grid-template-columns: 1fr auto; } .cv-job-meta, .cv-stage { display: none; } .cv-title { font-size: 26px; } }
"""

JS_BODY = r"""
  if (!window.__m28Cv) {
    window.__m28Cv = true;
    const cvSet = (el, v) => {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    const cvGo = (where) => {
      const box = document.querySelector('#m28-go textarea, #m28-go input');
      const btn = document.getElementById('m28-go-btn');
      if (!box || !btn) { return; }
      cvSet(box, where);
      setTimeout(() => btn.click(), 40);
    };
    const cvAct = (payload, tries) => {
      const box = document.querySelector('#dot-act textarea, #dot-act input');
      const btn = document.getElementById('dot-act-go');
      if (!box || !btn) {
        if (tries > 0) { setTimeout(() => cvAct(payload, tries - 1), 300); }
        return;
      }
      cvSet(box, JSON.stringify(Object.assign({ act: '', run: '', name: '', page: '', trash: '', entry: '', folder: '' }, payload)));
      setTimeout(() => btn.click(), 40);
    };
    window.m28DotAct = cvAct;
    const cvFinish = (run) => { cvGo('gop'); setTimeout(() => cvAct({ act: 'finish', run: run }, 12), 500); };   // trang Gộp & kết thúc của đợt, mở hộp Merge jobs & Finish
    document.addEventListener('click', (e) => {
      const t = e.target && e.target.closest ? e.target : null;
      if (!t) { return; }
      const f = t.closest('[data-cv-finish]');
      if (f) { e.preventDefault(); cvFinish(f.getAttribute('data-run') || ''); return; }
      const c = t.closest('[data-cv-check]');
      if (c) { e.preventDefault(); const b = document.getElementById('cv-check-go'); if (b) { b.click(); } return; }
      const ro = t.closest('[data-cv-reopen]');
      if (ro) {                                            // Fix again: chỉ gửi lệnh mở lại job. Dấu 'đã xem cảnh kết' xoá khi trang thấy job đang sửa (cvCheck),
        e.preventDefault();                                // nên lúc chờ không chạy lại cảnh kết / tự sang Gộp; mở lại lỗi thì vẫn ở trang này
        if (ro.disabled) { return; }
        ro.disabled = true;
        ro.textContent = 'Đang mở lại…';
        const done = document.querySelector('#cv-status .cv-all-done'); if (done) { done.remove(); }
        const h = document.querySelector('#cv-hero .cv-hero');
        if (h && !cvFinT) { h.classList.remove('cv-finale', 'cv-fin-end'); }
        const b = document.getElementById('cv-reopen-go'); if (b) { b.click(); }
        return;
      }
      const g = t.closest('#cv-status [data-go]');
      if (g) { e.preventDefault(); cvGo(g.getAttribute('data-go')); }
    });
    const cvOn = () => {
      const t = document.querySelector('#tabs button[role="tab"][aria-selected="true"]');
      return !!t && t.getAttribute('data-tab-id') === 'cvat';
    };
    const CV_FINALE_MS = 3700;                   // cảnh kết (CSS .cv-finale, 3400 ms) + chút nghỉ rồi mới sang Gộp & kết thúc
    let cvFinT = null;
    const cvFinale = (run) => {
      // màn chuyển đen, hình nộm hiện lên ở giữa, Yasuo hiện ra lướt qua (tay trên chuôi), ra khỏi khung thì hình nộm hiện vết chém và tách đôi
      const hero = document.querySelector('#cv-hero .cv-hero');
      let reduce = false;
      try { reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (err) { reduce = false; }
      if (!hero || reduce) { cvFinish(run); return; }
      hero.classList.remove('cv-finale', 'cv-fin-end');
      void hero.getBoundingClientRect();                   // gắn lại lớp: hoạt cảnh chạy lại từ đầu
      hero.classList.add('cv-finale');
      clearTimeout(cvFinT);
      cvFinT = setTimeout(() => { cvFinT = null; hero.classList.add('cv-fin-end'); cvFinish(run); }, CV_FINALE_MS);   // giữ khung cuối: quay lại tab không chạy lại hoạt cảnh
    };
    const cvCheck = () => {
      const m = document.querySelector('#cv-status .cv-all-done');
      if (!m) {                                             // không còn 'mọi job đã xong' (task mới, đã gộp...): bỏ cảnh kết nếu không đang chạy
        const h = document.querySelector('#cv-hero .cv-hero.cv-finale');
        if (h && !cvFinT) { h.classList.remove('cv-finale', 'cv-fin-end'); }
        const w = document.querySelector('#cv-status .cv-watch[data-open="1"]');
        if (w) {                                            // job đang sửa (Fix again, hoặc mở lại ngay trên CVAT): xong lần nữa thì cảnh kết chạy lại
          const k0 = 'm28_cv_done_' + (w.getAttribute('data-key') || '');
          try { sessionStorage.removeItem(k0); } catch (err) { }
          window[k0] = 0;
        }
        return;
      }
      if (!cvOn()) { return; }
      const k = 'm28_cv_done_' + (m.getAttribute('data-key') || '');
      let seen = false;
      try { seen = !!sessionStorage.getItem(k); sessionStorage.setItem(k, '1'); } catch (err) { seen = !!window[k]; window[k] = 1; }
      if (!seen) { cvFinale(m.getAttribute('data-run') || ''); return; }
      const h = document.querySelector('#cv-hero .cv-hero');      // đã xem cảnh kết rồi (quay lại tab, tải lại trang): giữ khung cuối, hình nộm đã tách đôi
      if (h && !cvFinT && !h.classList.contains('cv-finale')) { h.classList.add('cv-finale', 'cv-fin-end'); }
    };
    let cvQ = false;
    new MutationObserver(() => { if (!cvQ) { cvQ = true; setTimeout(() => { cvQ = false; cvCheck(); }, 250); } })
      .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-selected'] });
  }
"""
