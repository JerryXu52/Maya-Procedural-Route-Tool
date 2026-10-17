"""The interface every mode's generator follows, so the UI can drive a
cable, fence or road the same way."""


class BaseGenerator(object):
    mode = None

    def build(self, route, settings):
        """Create the live setup for a route. Returns the group node."""
        raise NotImplementedError

    def update(self, settings):
        """Push live settings onto an existing build."""
        raise NotImplementedError

    def bake(self):
        """Freeze the build into static geometry (week 3)."""
        raise NotImplementedError

    def delete(self):
        """Remove every node this build created."""
        raise NotImplementedError
