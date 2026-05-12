import os

def rewrite_docker_url(url: str) -> str:
    """
    Rewrites localhost to host.docker.internal if running inside a Docker container.
    """
    if not os.path.exists("/.dockerenv"):
        return url
        
    if "localhost" in url:
        return url.replace("localhost", "host.docker.internal")
            
    return url
