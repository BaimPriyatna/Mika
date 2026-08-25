from rich.console import Console
from rich.theme import Theme

MIKROTIK_THEME = Theme({
    "info":           "cyan",
    "success":        "bold green",
    "warning":        "bold yellow",
    "error":          "bold red",
    "step":           "bold magenta",
    "highlight":      "bold violet",

    "router_online":  "bold green",
    "router_offline": "bold red",
    "router_name":    "bold cyan",
    "interface_up":   "green",
    "interface_down": "red",
    "ip_addr":        "bold white",
    "mac_addr":       "dim white",

    "metric_label":   "cyan",
    "metric_val":     "bold white",
    "metric_pos":     "bold green",
    "metric_neg":     "bold red",
    "metric_neutral": "dim white",
    "badge_pass":     "bold green",
    "badge_fail":     "bold red",
    "badge_warn":     "bold yellow",

    "border":         "#3d3d3d",
    "border_accent":  "magenta",
    "separator":      "#2a2a2a",
    "muted":          "dim white",
    "timestamp":      "dim white",
    "label":          "#888888",

    "brand_hi":       "bold #c084fc",
    "brand_lo":       "bold #7c3aed",
    "brand_accent":   "bold #06b6d4",
})

console = Console(theme=MIKROTIK_THEME, highlight=False, force_terminal=True)


class Symbols:
    
    INFO    = "◆"
    SUCCESS = "✓"
    WARNING = "⚠"
    ERROR   = "✗"
    STEP    = "›"

    ARROW      = "→"
    ARROW_UP   = "↑"
    ARROW_DOWN = "↓"
    DOT        = "·"
    BULLET     = "•"
    CURSOR     = "❯"

    TEE   = "├─"
    ELBOW = "└─"
    PIPE  = "│ "
    BLANK = "  "

    DIAMOND      = "◈"
    LBRACKET     = "❮"
    RBRACKET     = "❯"
    
    ROUTER       = "◉"
    INTERFACE    = "⚡"
    FIREWALL     = "🛡"
    HOTSPOT      = "📶"
    VPN          = "🔒"

    LINE_THIN    = "─"
    LINE_DOUBLE  = "═"
    
    BAR_FULL     = "█"
    BAR_HALF     = "▌"
    BAR_LIGHT    = "░"
    BAR_MEDIUM   = "▒"
    BAR_DARK     = "▓"
