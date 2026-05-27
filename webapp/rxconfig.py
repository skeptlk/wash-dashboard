import reflex as rx

config = rx.Config(
    app_name="webapp",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)