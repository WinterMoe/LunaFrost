

const ReadingPreferences = {

    defaults: {
        colorMode: 'light',
        fontSize: 16,
        lineHeight: '1.8',
        fontFamily: 'var(--font-serif)',
        readingWidth: '720px',
        textAlignment: 'left'
    },

    current: null,

    async init() {

        await this.load();

        this.apply(this.current);

    },

    async load() {
        try {

            const response = await fetch('/api/reading-preferences');
            const data = await response.json();

            if (data.success && data.preferences) {
                this.current = data.preferences;

                this.saveToLocalStorage(this.current);
                return this.current;
            }
        } catch (error) {
            console.warn('[ReadingPrefs] Failed to load from API, using localStorage or defaults:', error);
        }

        const cached = this.loadFromLocalStorage();
        if (cached) {
            this.current = cached;
            return this.current;
        }

        this.current = { ...this.defaults };
        return this.current;
    },

    async save(prefs) {
        this.current = { ...this.current, ...prefs };

        this.saveToLocalStorage(this.current);

        try {
            const response = await window.fetchWithCSRF('/api/reading-preferences', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(this.current)
            });

            const data = await response.json();
            if (!data.success) {
                console.error('[ReadingPrefs] Failed to save to API:', data.error);
            }
        } catch (error) {
            console.error('[ReadingPrefs] Error saving to API:', error);
        }
    },

    apply(prefs) {
        if (!prefs) prefs = this.current || this.defaults;

        this.applyColorMode(prefs.colorMode);

        const textElements = document.querySelectorAll('.text-content, .panel-content');
        textElements.forEach(element => {
            element.style.fontSize = `${prefs.fontSize}px`;
            element.style.lineHeight = prefs.lineHeight;
            element.style.fontFamily = prefs.fontFamily;
            element.style.maxWidth = prefs.readingWidth;
            element.style.textAlign = prefs.textAlignment;
        });
    },

    applyColorMode(mode) {

        document.documentElement.classList.remove('dark-mode', 'sepia-mode', 'high-contrast-mode');
        document.body.classList.remove('dark-mode', 'sepia-mode', 'high-contrast-mode');

        if (mode === 'dark') {
            document.documentElement.classList.add('dark-mode');
            document.body.classList.add('dark-mode');
        } else if (mode === 'sepia') {
            document.documentElement.classList.add('sepia-mode');
            document.body.classList.add('sepia-mode');
        } else if (mode === 'high-contrast') {
            document.documentElement.classList.add('high-contrast-mode');
            document.body.classList.add('high-contrast-mode');
        }

    },

    saveToLocalStorage(prefs) {
        try {
            localStorage.setItem('lf_reading_prefs', JSON.stringify(prefs));
        } catch (e) {
            console.warn('[ReadingPrefs] Failed to save to localStorage:', e);
        }
    },

    loadFromLocalStorage() {
        try {
            const saved = localStorage.getItem('lf_reading_prefs');
            if (saved) {
                return { ...this.defaults, ...JSON.parse(saved) };
            }
        } catch (e) {
            console.warn('[ReadingPrefs] Failed to load from localStorage:', e);
        }
        return null;
    },

    async reset() {
        this.current = { ...this.defaults };
        await this.save(this.current);
        this.apply(this.current);
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        ReadingPreferences.init();
    });
} else {
    ReadingPreferences.init();
}

window.ReadingPreferences = ReadingPreferences;
