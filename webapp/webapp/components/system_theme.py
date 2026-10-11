"""Follow device theme changes, including after a manual theme toggle."""

import reflex as rx


class SystemTheme(rx.Fragment):
    """App-wide listener; manual toggles last until the OS theme changes."""

    def add_imports(self):
        return {
            "react": ["useEffect"],
            "$/utils/react-theme": ["useTheme"],
        }

    def add_hooks(self):
        return [
            "const { setTheme: setDeviceTheme } = useTheme();",
            """
useEffect(() => {
    // Discard a saved manual choice when opening the app. Reflex also reads
    // this key during its theme provider's initialization.
    localStorage.setItem("theme", "system");
    setDeviceTheme("system");

    const preference = window.matchMedia("(prefers-color-scheme: dark)");
    const followDeviceTheme = () => setDeviceTheme("system");
    preference.addEventListener("change", followDeviceTheme);
    return () => preference.removeEventListener("change", followDeviceTheme);
}, [setDeviceTheme]);
""",
        ]
