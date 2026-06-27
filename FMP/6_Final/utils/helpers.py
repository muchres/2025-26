"""Small shared helper utilities used across dashboards."""


def rgba(hex_color, alpha):
    """Convert a #RRGGBB hex colour to an rgba() string with the given alpha."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def hex_to_rgb(hex_color):
    """Convert a #RRGGBB hex colour to an (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
