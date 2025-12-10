document.addEventListener('DOMContentLoaded', function () {
    const charactersContainer = document.getElementById('characters-container');
    const addCharacterBtn = document.getElementById('add-character-btn');
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    const alertContainer = document.getElementById('alert-container');
    const loadingOverlay = document.getElementById('loading-overlay');

    if (!window.webtoonSettingsData) {
        console.error('webtoonSettingsData is not defined');
        window.webtoonSettingsData = { jobId: '', glossaryLength: 0 };
    }

    let charCounter = window.webtoonSettingsData.glossaryLength || 0;

    // Toggle character entry expansion
    document.addEventListener('click', function (e) {
        const header = e.target.closest('.character-header');
        if (header && !e.target.closest('.btn-remove-char')) {
            const entry = header.closest('.character-entry');
            entry.classList.toggle('collapsed');
            entry.classList.toggle('expanded');
        }
    });

    // Add new character manually
    if (addCharacterBtn) {
        addCharacterBtn.addEventListener('click', function () {
            charCounter++;
            const newEntry = createCharacterEntry('', '', 'auto', true, true);
            charactersContainer.appendChild(newEntry);
            removeEmptyMessage();
        });
    }

    // Remove character
    document.addEventListener('click', function (e) {
        const removeBtn = e.target.closest('.btn-remove-char');
        if (removeBtn) {
            e.stopPropagation();
            if (confirm('Remove this character?')) {
                const entry = removeBtn.closest('.character-entry');
                if (entry) {
                    entry.remove();
                    if (charactersContainer.querySelectorAll('.character-entry').length === 0) {
                        showEmptyMessage();
                    }
                }
            }
        }
    });

    // Validating input to confirm no weird chars if needed? 
    // Just update summary on input
    document.addEventListener('input', function (e) {
        if (e.target.classList.contains('char-korean') ||
            e.target.classList.contains('char-english') ||
            e.target.classList.contains('char-gender')) {

            const entry = e.target.closest('.character-entry');
            updateCharacterSummary(entry);
        }
    });

    // Save Glossary
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', async function () {
            const glossary = {};
            const entries = charactersContainer.querySelectorAll('.character-entry');

            entries.forEach(function (entry, index) {
                const koreanName = entry.querySelector('.char-korean').value.trim();
                const englishName = entry.querySelector('.char-english').value.trim();
                const gender = entry.querySelector('.char-gender').value;
                const description = entry.querySelector('.char-description').value.trim();

                // Using timestamp + index for unique ID if it's new, otherwise keep existing if we tracked it?
                // Actually novel glossary re-generates IDs on save based on iteration usually or simple keys.
                // The implementation in novel_settings.js uses 'char_' + index. 
                // This means IDs are not stable across saves if order changes. 
                // For webtoon simple usage this is fine for now.

                if (koreanName || englishName) {
                    // Use a more stable ID if possible, but 'char_' + index is what novel does.
                    // Let's stick to the pattern.
                    glossary['char_' + index] = {
                        korean_name: koreanName,
                        english_name: englishName,
                        gender: gender,
                        description: description
                    };
                }
            });

            saveSettingsBtn.disabled = true;
            const originalText = saveSettingsBtn.innerHTML;
            saveSettingsBtn.innerHTML = 'Saving...';

            try {
                const jobId = window.webtoonSettingsData.jobId;
                // Use fetchWithCSRF if available, otherwise fallback to fetch
                const fetchFn = window.fetchWithCSRF || fetch;

                const response = await fetchFn('/api/webtoon/job/' + encodeURIComponent(jobId) + '/glossary', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ glossary: glossary })
                });

                const data = await response.json();

                if (data.success) {
                    showAlert('✓ Character glossary saved! (' + Object.keys(glossary).length + ' characters)', 'success');
                    setTimeout(function () {
                        location.reload();
                    }, 1500);
                } else {
                    showAlert('Error: ' + (data.error || 'Failed to save glossary'), 'error');
                }
            } catch (error) {
                console.error('Error saving glossary:', error);
                showAlert('Error: ' + error.message, 'error');
            } finally {
                saveSettingsBtn.disabled = false;
                saveSettingsBtn.innerHTML = originalText;
            }
        });
    }

    // Helper: Create Character Entry HTML
    function createCharacterEntry(koreanName, englishName, gender, expanded, isNew = false) {
        const entry = document.createElement('div');
        entry.className = 'character-entry ' + (expanded ? 'expanded' : 'collapsed');
        if (isNew) {
            entry.dataset.isNew = 'true';
        }

        const escapeHtml = function (text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        const safeKoreanName = escapeHtml(koreanName);
        const safeEnglishName = escapeHtml(englishName);
        const displayKoreanName = escapeHtml(koreanName || '(Empty)');
        const displayEnglishName = escapeHtml(englishName || '(Not set)');

        if (!gender) gender = 'auto';

        let genderBadgeHtml = '';
        let genderDisplayText = '';

        if (gender === 'auto') {
            genderBadgeHtml = '<span class="gender-badge gender-auto">AI Auto-select</span>';
            genderDisplayText = 'AI Auto-select';
        } else if (gender === 'male') {
            genderBadgeHtml = '<span class="gender-badge gender-male">he/him</span>';
            genderDisplayText = 'he/him';
        } else if (gender === 'female') {
            genderBadgeHtml = '<span class="gender-badge gender-female">she/her</span>';
            genderDisplayText = 'she/her';
        } else if (gender === 'other') {
            genderBadgeHtml = '<span class="gender-badge gender-other">they/them</span>';
            genderDisplayText = 'they/them';
        }

        const newBadgeHtml = isNew ? '<span class="new-character-badge">NEW</span>' : '';

        const headerHtml = `
            <div class="character-header">
                <div class="character-summary">
                    <span class="korean-name">${displayKoreanName}</span>
                    <span class="arrow">→</span>
                    <span class="english-name">${displayEnglishName}</span>
                    ${newBadgeHtml}
                    ${genderBadgeHtml}
                </div>
                <div class="character-actions">
                    <button class="btn btn-danger btn-remove-char">✕</button>
                    <span class="expand-icon">▼</span>
                </div>
            </div>`;

        const detailsHtml = `
            <div class="character-details">
                <div class="form-group">
                    <label>Original Name (Korean/Japanese)</label>
                    <input type="text" class="char-korean" placeholder="e.g., 田中 (Tanaka)" value="${safeKoreanName}">
                </div>
                <div class="form-group">
                    <label>English Name (Translation)</label>
                    <input type="text" class="char-english" placeholder="e.g., Tanaka" value="${safeEnglishName}">
                </div>
                <div class="form-group">
                    <label>Gender / Pronouns</label>
                    <select class="char-gender">
                        <option value="auto"${gender === 'auto' ? ' selected' : ''}>AI Auto-select (recommended)</option>
                        <option value="male"${gender === 'male' ? ' selected' : ''}>Male (he/him)</option>
                        <option value="female"${gender === 'female' ? ' selected' : ''}>Female (she/her)</option>
                        <option value="other"${gender === 'other' ? ' selected' : ''}>Other (they/them)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Description (Optional)</label>
                    <textarea class="char-description" placeholder="e.g., Main protagonist, student">${''}</textarea>
                    <p class="help-text">Context to help the AI translate consistently.</p>
                </div>
            </div>`;

        entry.innerHTML = headerHtml + detailsHtml;
        return entry;
    }

    function updateCharacterSummary(entry) {
        const escapeHtml = str => {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        };

        const koreanName = escapeHtml(entry.querySelector('.char-korean').value.trim() || '(Empty)');
        const englishName = escapeHtml(entry.querySelector('.char-english').value.trim() || '(Not set)');
        const gender = entry.querySelector('.char-gender').value;
        const isNew = entry.dataset.isNew === 'true';

        const summary = entry.querySelector('.character-summary');
        let genderBadgeClass = 'gender-auto';
        let genderBadgeText = 'AI Auto-select';

        if (gender === 'male') { genderBadgeClass = 'gender-male'; genderBadgeText = 'he/him'; }
        else if (gender === 'female') { genderBadgeClass = 'gender-female'; genderBadgeText = 'she/her'; }
        else if (gender === 'other') { genderBadgeClass = 'gender-other'; genderBadgeText = 'they/them'; }

        const newBadgeHtml = isNew ? '<span class="new-character-badge">NEW</span>' : '';
        const genderHtml = `<span class="gender-badge ${genderBadgeClass}">${genderBadgeText}</span>`;

        summary.innerHTML = `
            <span class="korean-name">${koreanName}</span>
            <span class="arrow">→</span>
            <span class="english-name">${englishName}</span>
            ${newBadgeHtml}
            ${genderHtml}
        `;
    }

    function removeEmptyMessage() {
        const emptyMessage = document.getElementById('empty-message');
        if (emptyMessage) emptyMessage.remove();
    }

    function showEmptyMessage() {
        charactersContainer.innerHTML = '<p id="empty-message" style="text-align: center; color: #718096; padding: 40px;">No characters added yet. Click "Add Character Manually" to get started.</p>';
    }

    function showAlert(message, type) {
        if (window.showAlertModal) {
            const title = type === 'success' ? 'Success' : (type === 'error' ? 'Error' : 'Notice');
            // Map simple types to modal types if needed, but 'success'/'error' matches.
            window.showAlertModal(title, message, type);
        } else {
            console.log(type.toUpperCase() + ": " + message);
            alert(message);
        }
    }
});
