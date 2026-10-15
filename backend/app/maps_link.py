""""Open in Google Maps" links. Plain URLs: no API key, no API calls."""

from urllib.parse import urlencode


def google_maps_url(name: str, address: str | None, lat: float, lng: float) -> str:
    """Search by name + address so Google opens the listing (website, hours, photos).

    For approximate places the address is just a city, which still finds most pop-ups
    with an online presence. Without an address, fall back to the pin's coordinates.
    """
    query = f"{name}, {address}" if address else f"{lat},{lng}"
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": query})
