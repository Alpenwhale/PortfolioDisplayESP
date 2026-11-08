"""Entry point. Draws a test screen for now."""
import config
from display import create_display
from display.base import Display


def draw_test(d: Display) -> None:
    """Dummy portfolio screen."""
    black = d.rgb(0, 0, 0)
    white = d.rgb(255, 255, 255)
    green = d.rgb(0, 200, 80)
    red = d.rgb(220, 40, 40)

    d.fill(black)
    d.text("PortfolioDisplay", 8, 8, white, black, scale=2)
    d.fill_rect(8, 30, d.width - 16, 2, white)
    d.text("AAPL  +1.23%", 8, 48, green, black, scale=2)
    d.text("TSLA  -0.87%", 8, 72, red, black, scale=2)
    d.show()


d = create_display(config)
draw_test(d)
print("display ok:", d.width, "x", d.height)
