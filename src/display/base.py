"""Common display interface."""


class Display:
    """Base for all displays. Colors are whatever rgb() returns."""

    width: int = 0
    height: int = 0

    def rgb(self, r: int, g: int, b: int) -> int:
        """Convert 8-bit RGB to native color."""
        raise NotImplementedError

    def fill(self, color: int) -> None:
        """Fill whole screen."""
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        """Fill a rectangle."""
        raise NotImplementedError

    def text(self, s: str, x: int, y: int, color: int, bg: int = 0, scale: int = 1) -> None:
        """Draw text with the builtin 8x8 font."""
        raise NotImplementedError

    def show(self) -> None:
        """Flush buffer. No-op for unbuffered displays."""
