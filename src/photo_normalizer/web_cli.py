#!/usr/bin/env python3
"""CLI entry point for the Photo Normalizer web interface."""

import click
from .web_app import run_web_app


@click.command()
@click.option('--host', default='127.0.0.1', help='Host to run the server on')
@click.option('--port', default=5000, type=int, help='Port to run the server on')
@click.option('--debug/--no-debug', default=False, help='Enable debug mode')
def main(host: str, port: int, debug: bool):
    """Start the Photo Normalizer web interface."""
    click.echo(f"Starting Photo Normalizer web interface...")
    click.echo(f"Open your browser to: http://{host}:{port}")
    click.echo("Press Ctrl+C to stop the server")
    
    try:
        run_web_app(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")


if __name__ == '__main__':
    main()
