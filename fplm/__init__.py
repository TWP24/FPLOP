"""fplm — Fantasy Premier League team builder optimised for monthly prizes."""
import warnings

# macOS system Python links LibreSSL; urllib3 warns on import and it is just noise here.
warnings.filterwarnings("ignore", message=".*OpenSSL.*")

__version__ = "1.0.0"
