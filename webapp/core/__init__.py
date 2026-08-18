"""Shared spine — everything here is hazard-agnostic on purpose.

Nothing in this package may know what a landslide is. A module that imports
`products.landslide` from here has put the spine on top of one product, which
is the exact mistake this layout exists to prevent: the second product then
either inherits the first one's assumptions or forks the code.

The test is simple. If FloodSense cannot use it unchanged, it belongs in a
product folder, not here.
"""
