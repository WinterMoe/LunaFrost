document.addEventListener('DOMContentLoaded', function () {
    const charactersContainer = document.getElementById('characters-container');
    const addCharacterBtn = document.getElementById('add-character-btn');
    const autoDetectBtn = document.getElementById('auto-detect-btn');
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    const alertContainer = document.getElementById('alert-container');
    const loadingOverlay = document.getElementById('loading-overlay');

    if (!window.novelSettingsData) {
        console.error('novelSettingsData is not defined');
        window.novelSettingsData = { novelId: '', chapterIndex: null, glossaryLength: 0, chapterText: '', totalChapters: 0 };
    }

    let charCounter = window.novelSettingsData.glossaryLength || 0;

    document.addEventListener('click', function (e) {
        const header = e.target.closest('.character-header');
        if (header && !e.target.closest('.btn-remove-char')) {
            const entry = header.closest('.character-entry');
            entry.classList.toggle('collapsed');
            entry.classList.toggle('expanded');
        }
    });

    if (addCharacterBtn) {
        addCharacterBtn.addEventListener('click', function () {
            charCounter++;
            const newEntry = createCharacterEntry('', '', 'auto', true, true);
            charactersContainer.appendChild(newEntry);
            removeEmptyMessage();
        });
    }

    if (autoDetectBtn) {
        autoDetectBtn.addEventListener('click', async function () {
            loadingOverlay.style.display = 'flex';

            try {
                const novelId = window.novelSettingsData.novelId;
                const chapterNumber = window.novelSettingsData.chapterNumber;

                const requestBody = {};

                if (chapterNumber !== null && chapterNumber !== undefined) {
                    requestBody.chapter_number = chapterNumber;
                }

                const response = await window.fetchWithCSRF('/api/novel/' + encodeURIComponent(novelId) + '/auto-detect-characters', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });

                const data = await response.json();

                if (data.success && data.characters) {

                    const existingNames = new Set();
                    charactersContainer.querySelectorAll('.char-korean').forEach(input => {
                        if (input.value.trim()) {
                            existingNames.add(input.value.trim());
                        }
                    });

                    let addedCount = 0;
                    let skippedCount = 0;

                    data.characters.forEach(function (koreanName) {
                        if (existingNames.has(koreanName)) {
                            skippedCount++;
                            return;
                        }

                        const englishName = data.translations && data.translations[koreanName]
                            ? data.translations[koreanName]
                            : '';

                        const gender = data.genders && data.genders[koreanName]
                            ? data.genders[koreanName]
                            : 'auto';

                        const entry = createCharacterEntry(koreanName, englishName, gender, false, true);
                        charactersContainer.appendChild(entry);
                        charCounter++;
                        addedCount++;
                    });

                    removeEmptyMessage();

                    let message = '✔ Auto-detected ' + addedCount + ' new character(s)!';

                    if (skippedCount > 0) {
                        message += ' (Skipped ' + skippedCount + ' duplicate(s))';
                    }

                    if (data.chapter_scanned !== undefined) {
                        if (typeof data.chapter_scanned === 'number') {
                            message += '\n\nScanned: Chapter ' + (data.chapter_scanned + 1);
                        } else {
                            message += '\n\nScanned: ' + data.chapter_scanned;
                        }
                    }

                    if (data.stats) {
                        message += '\n\nDetection stats:';

                        if (data.stats.detection_mode) {
                            message += '\n• Mode: ' + data.stats.detection_mode;
                        }

                        if (data.stats.detection_mode === 'bilingual') {
                            message += '\n• English names found: ' + (data.stats.english_names_found || 0);
                            message += '\n• Korean mapped: ' + (data.stats.korean_mapped || 0);
                            message += '\n• Final count: ' + (data.stats.final_count || 0);
                        }

                        else if (data.stats.detection_mode === 'korean_only') {
                            message += '\n• AI detected: ' + (data.stats.ai_detected || 0);
                            message += '\n• Pattern detected: ' + (data.stats.pattern_detected || 0);
                            message += '\n• After deduplication: ' + (data.stats.final_count || 0);
                        }

                        else {
                            if (data.stats.ai_detected !== undefined) {
                                message += '\n• AI detected: ' + data.stats.ai_detected;
                            }
                            if (data.stats.pattern_detected !== undefined) {
                                message += '\n• Pattern detected: ' + data.stats.pattern_detected;
                            }
                            if (data.stats.final_count !== undefined) {
                                message += '\n• Final count: ' + data.stats.final_count;
                            }
                        }
                    }

                    if (data.debug_info) {
                        message += '\n\nDebug Info:';
                        message += '\n• Trans Length: ' + data.debug_info.translated_text_length;
                        message += '\n• Has Trans: ' + data.debug_info.has_translation;
                    }

                    showAlert(message, 'success');
                } else {
                    showAlert('Error: ' + (data.error || 'Failed to detect characters'), 'error');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            } finally {
                loadingOverlay.style.display = 'none';
            }
        });
    }

    document.addEventListener('click', function (e) {
        const removeBtn = e.target.closest('.btn-remove-char');
        if (removeBtn) {
            e.stopPropagation();
            const entry = removeBtn.closest('.character-entry');
            if (entry) {
                entry.remove();

                if (charactersContainer.querySelectorAll('.character-entry').length === 0) {
                    showEmptyMessage();
                }
            }
        }
    });

    document.addEventListener('input', function (e) {
        if (e.target.classList.contains('char-korean') ||
            e.target.classList.contains('char-english') ||
            e.target.classList.contains('char-gender')) {

            const entry = e.target.closest('.character-entry');
            updateCharacterSummary(entry);
        }
    });

    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', async function () {
            const glossary = {};
            const entries = charactersContainer.querySelectorAll('.character-entry');

            entries.forEach(function (entry, index) {
                const koreanName = entry.querySelector('.char-korean').value.trim();
                const englishName = entry.querySelector('.char-english').value.trim();
                const gender = entry.querySelector('.char-gender').value;
                const description = entry.querySelector('.char-description').value.trim();

                if (koreanName || englishName) {
                    glossary['char_' + index] = {
                        korean_name: koreanName,
                        english_name: englishName,
                        gender: gender,
                        description: description
                    };
                }
            });

            try {

                const novelId = window.novelSettingsData.novelId;
                let response = await window.fetchWithCSRF('/api/novel/' + encodeURIComponent(novelId) + '/glossary', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ glossary: glossary })
                });

                let data = await response.json();

                if (data.success) {
                    showAlert('✓ Character glossary saved! (' + Object.keys(glossary).length + ' characters)', 'success');

                    setTimeout(function () {
                        location.reload();
                    }, 1500);
                } else {
                    showAlert('Error: ' + (data.error || 'Failed to save glossary'), 'error');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            }
        });
    }

    function createCharacterEntry(koreanName, englishName, gender, expanded, isNew = false) {
        const entry = document.createElement('div');
        entry.className = 'character-entry ' + (expanded ? 'expanded' : 'collapsed');
        if (isNew) {
            entry.dataset.isNew = 'true';
        } else {
            delete entry.dataset.isNew;
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
        } else {
            genderBadgeHtml = '<span class="gender-badge gender-auto">AI Auto-select</span>';
            genderDisplayText = 'AI Auto-select';
        }

        const newBadgeHtml = isNew ? '<span class="new-character-badge">NEW</span>' : '';

        const headerHtml =
            '<div class="character-header">' +
            '<div class="character-summary">' +
            '<span class="korean-name">' + displayKoreanName + '</span>' +
            '<span class="arrow">→</span>' +
            '<span class="english-name">' + displayEnglishName + '</span>' +
            newBadgeHtml +
            genderBadgeHtml +
            '</div>' +
            '<div class="character-actions">' +
            '<button class="btn btn-danger btn-remove-char">✕</button>' +
            '<span class="expand-icon">▼</span>' +
            '</div>' +
            '</div>';

        const detailsHtml =
            '<div class="character-details">' +
            '<div class="form-group">' +
            '<label>Korean Name (Original)</label>' +
            '<input type="text" class="char-korean" placeholder="e.g., 김철수" value="' + safeKoreanName + '">' +
            '</div>' +
            '<div class="form-group">' +
            '<label>English Name (Translation)</label>' +
            '<input type="text" class="char-english" placeholder="e.g., John Kim" value="' + safeEnglishName + '">' +
            '</div>' +
            '<div class="form-group">' +
            '<label>Gender / Pronouns</label>' +
            '<select class="char-gender">' +
            '<option value="auto"' + (gender === 'auto' ? ' selected' : '') + '>AI Auto-Select</option>' +
            '<option value="male"' + (gender === 'male' ? ' selected' : '') + '>Male (he/him)</option>' +
            '<option value="female"' + (gender === 'female' ? ' selected' : '') + '>Female (she/her)</option>' +
            '<option value="other"' + (gender === 'other' ? ' selected' : '') + '>Other (they/them)</option>' +
            '</select>' +
            '<p class="help-text">AI Auto-select lets the translator determine the best pronouns based on context</p>' +
            '</div>' +
            '<div class="form-group">' +
            '<label>Description (Optional)</label>' +
            '<textarea class="char-description" placeholder="e.g., Main protagonist, skilled swordsman, age 25"></textarea>' +
            '<p class="help-text">Additional context to help the AI translate consistently. Supports <strong>Markdown</strong> (e.g., **bold**, *italic*).</p>' +
            '</div>' +
            '</div>';

        entry.innerHTML = headerHtml + detailsHtml;
        return entry;
    }

    function updateCharacterSummary(entry) {
        const escapeHtml = function (text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        };

        const koreanName = escapeHtml(entry.querySelector('.char-korean').value.trim() || '(Empty)');
        const englishName = escapeHtml(entry.querySelector('.char-english').value.trim() || '(Not set)');
        const gender = entry.querySelector('.char-gender').value;
        const isNew = entry.dataset.isNew === 'true';

        const summary = entry.querySelector('.character-summary');

        let genderBadgeClass = 'gender-auto';
        let genderBadgeText = 'AI Auto-select';

        if (gender === 'auto') {
            genderBadgeClass = 'gender-auto';
            genderBadgeText = 'AI Auto-select';
        } else if (gender === 'male') {
            genderBadgeClass = 'gender-male';
            genderBadgeText = 'he/him';
        } else if (gender === 'female') {
            genderBadgeClass = 'gender-female';
            genderBadgeText = 'she/her';
        } else if (gender === 'other') {
            genderBadgeClass = 'gender-other';
            genderBadgeText = 'they/them';
        }

        const newBadgeHtml = isNew ? '<span class="new-character-badge">NEW</span>' : '';

        summary.innerHTML =
            '<span class="korean-name">' + koreanName + '</span>' +
            '<span class="arrow">→</span>' +
            '<span class="english-name">' + englishName + '</span>' +
            newBadgeHtml +
            '<span class="gender-badge ' + genderBadgeClass + '">' + genderBadgeText + '</span>';
    }

    function removeEmptyMessage() {
        const emptyMessage = document.getElementById('empty-message');
        if (emptyMessage) {
            emptyMessage.remove();
        }
    }

    function showEmptyMessage() {
        charactersContainer.innerHTML = '<p id="empty-message" style="text-align: center; color: #718096; padding: 40px;">No characters added yet. Click "Add Character Manually" or "Auto-Detect Characters" to get started.</p>';
    }

    function showAlert(message, type) {

        let modalType = 'info';
        if (type === 'success') modalType = 'success';
        if (type === 'danger' || type === 'error') modalType = 'error';

        if (window.showAlertModal) {
            const title = type === 'success' ? 'Success' : (type === 'error' ? 'Error' : 'Notice');
            window.showAlertModal(title, message, modalType);
        } else {

            alertContainer.innerHTML =
                '<div class="alert alert-' + type + '">' +
                message +
                '</div>';

            window.scrollTo({ top: 0, behavior: 'smooth' });

            setTimeout(function () {
                alertContainer.innerHTML = '';
            }, 5000);
        }
    }

    const generateShareBtn = document.getElementById('generate-share-btn');
    const revokeShareBtn = document.getElementById('revoke-share-btn');
    const copyShareLinkBtn = document.getElementById('copy-share-link-btn');
    const shareContainer = document.getElementById('share-container');
    const noShareContainer = document.getElementById('no-share-container');
    const shareLinkInput = document.getElementById('share-link-input');

    if (generateShareBtn) {
        generateShareBtn.addEventListener('click', async function () {
            try {
                const novelId = window.novelSettingsData.novelId;
                // Use fetchWithCSRF if available, otherwise fallback to fetch
                const fetchFn = window.fetchWithCSRF || fetch;

                const response = await fetchFn('/api/novel/' + encodeURIComponent(novelId) + '/share', {
                    method: 'POST'
                });
                const data = await response.json();

                if (data.success) {
                    shareLinkInput.value = data.share_url;
                    shareContainer.style.display = 'block';
                    noShareContainer.style.display = 'none';
                    showAlert('Link generated successfully!', 'success');
                } else {
                    showAlert('Error: ' + (data.error || 'Failed to generate link'), 'error');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'error');
            }
        });
    }

    if (revokeShareBtn) {
        revokeShareBtn.addEventListener('click', async function () {
            if (window.showConfirmationModal) {
                window.showConfirmationModal(
                    'Revoke Share Link?',
                    'Are you sure you want to revoke this link? Anyone with the link will no longer be able to access the novel.',
                    async () => {
                        await performRevoke();
                    },
                    'warning'
                );
            } else {
                if (confirm('Are you sure you want to revoke this link? Anyone with the link will no longer be able to access the novel.')) {
                    await performRevoke();
                }
            }
        });
    }

    async function performRevoke() {
        try {
            const novelId = window.novelSettingsData.novelId;
            const fetchFn = window.fetchWithCSRF || fetch;

            const response = await fetchFn('/api/novel/' + encodeURIComponent(novelId) + '/unshare', {
                method: 'POST'
            });
            const data = await response.json();

            if (data.success) {
                shareContainer.style.display = 'none';
                noShareContainer.style.display = 'block';
                showAlert('Link revoked successfully!', 'success');
            } else {
                showAlert('Error: ' + (data.error || 'Failed to revoke link'), 'error');
            }
        } catch (error) {
            showAlert('Error: ' + error.message, 'error');
        }
    }

    if (copyShareLinkBtn) {
        copyShareLinkBtn.addEventListener('click', function () {
            shareLinkInput.select();
            document.execCommand('copy');
            const originalText = copyShareLinkBtn.textContent;
            copyShareLinkBtn.textContent = 'Copied!';
            setTimeout(() => {
                copyShareLinkBtn.textContent = originalText;
            }, 2000);
        });
    }
});
