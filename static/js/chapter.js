document.addEventListener('DOMContentLoaded', function () {
    const translateBtn = document.getElementById('translate-btn');
    const thinkBtn = document.getElementById('think-btn');
    const compareBtn = document.getElementById('compare-btn');
    const saveBtn = document.getElementById('save-btn');
    const editBtn = document.getElementById('edit-btn');
    const textDisplay = document.getElementById('text-display');
    const editArea = document.getElementById('edit-area');
    const editTextarea = document.getElementById('edit-textarea');
    const saveEditBtn = document.getElementById('save-edit-btn');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const singleView = document.getElementById('single-view');
    const sideView = document.getElementById('side-by-side-view');
    const koreanPanel = document.getElementById('korean-panel');
    const englishPanel = document.getElementById('english-panel');
    const thinkingIndicator = document.getElementById('thinking-indicator');
    const tokenUsageDisplay = document.getElementById('token-usage-display');
    const inputTokensSpan = document.getElementById('input-tokens');
    const outputTokensSpan = document.getElementById('output-tokens');
    const totalTokensSpan = document.getElementById('total-tokens');

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    let koreanText = window.chapterData.koreanText;
    let translatedText = window.chapterData.translatedText;
    let translationModel = window.chapterData.translationModel;
    let chapterTitle = window.chapterData.title || '';
    let translatedTitle = window.chapterData.translatedTitle || '';
    let isTranslated = translatedText && translatedText.trim().length > 0;
    let isCompareMode = false;

    function isThinkingModel(modelName) {
        if (!modelName) return false;
        const lowerName = modelName.toLowerCase();
        return lowerName.includes('o1-') || lowerName.includes('thinking') || lowerName.includes('r1');
    }

    function updateTokenUsageDisplay(tokenUsage, costInfo = null) {
        if (!tokenUsage || !tokenUsageDisplay) return;

        const inputTokens = tokenUsage.input_tokens || 0;
        const outputTokens = tokenUsage.output_tokens || 0;
        const totalTokens = tokenUsage.total_tokens || (inputTokens + outputTokens);

        if (inputTokensSpan) inputTokensSpan.textContent = formatNumber(inputTokens);
        if (outputTokensSpan) outputTokensSpan.textContent = formatNumber(outputTokens);
        if (totalTokensSpan) totalTokensSpan.textContent = formatNumber(totalTokens);

        let costText = '';
        if (costInfo && costInfo.pricing_available && costInfo.total_cost !== null) {
            const cost = formatCost(costInfo.total_cost);
            if (cost) {
                costText = ` (Est. ${cost})`;
            }
        }

        const tokenBadge = tokenUsageDisplay.querySelector('.token-badge');
        if (tokenBadge && costText) {
            const existingCost = tokenBadge.querySelector('.cost-info');
            if (existingCost) {
                existingCost.textContent = costText;
            } else {
                const costSpan = document.createElement('span');
                costSpan.className = 'cost-info';
                costSpan.style.color = '#2c5282';
                costSpan.style.fontWeight = '500';
                costSpan.textContent = costText;
                tokenBadge.appendChild(costSpan);
            }
        }

        tokenUsageDisplay.classList.remove('hidden');
        tokenUsageDisplay.style.display = 'block';

        if (window.tokenUsageTimeout) {
            clearTimeout(window.tokenUsageTimeout);
        }

        if (!tokenUsageDisplay.hasAttribute('data-click-handler')) {
            tokenUsageDisplay.setAttribute('data-click-handler', 'true');
            tokenUsageDisplay.style.cursor = 'pointer';
            tokenUsageDisplay.title = 'Click to dismiss';
            tokenUsageDisplay.addEventListener('click', function () {
                this.style.display = 'none';
                this.classList.add('hidden');
            });
        }
    }

    function formatCost(cost) {
        if (cost < 0.01) {
            return `$${cost.toFixed(4)}`;
        } else if (cost < 1) {
            return `$${cost.toFixed(3)}`;
        } else {
            return `$${cost.toFixed(2)}`;
        }
    }

    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    function getStoredModelPricing() {

        return (async function () {
            try {
                const resp = await fetch('/api/pricing');
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.success && data.pricing) return data.pricing;
                }
            } catch (e) {

            }

            try {
                const raw = localStorage.getItem('lf_model_pricing');
                return raw ? JSON.parse(raw) : {};
            } catch (e) {
                console.warn('Error reading model pricing from localStorage', e);
                return {};
            }
        })();
    }

    function saveStoredModelPricing(obj) {

        (async function () {
            try {
                await window.fetchWithCSRF('/api/pricing', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(obj)
                });
            } catch (e) {
                console.warn('Error saving pricing to server', e);
            }

            try {
                localStorage.setItem('lf_model_pricing', JSON.stringify(obj));
            } catch (e) {
                console.warn('Error saving model pricing to localStorage', e);
            }
        })();
    }

    async function computeCostFromPricing(estimation, modelName) {
        try {
            if (!estimation) return null;
            const pricing = await getStoredModelPricing();
            const modelPricing = pricing[modelName] || pricing['default'] || null;
            if (!modelPricing) return null;

            const inputPricePer1k = parseFloat(modelPricing.input_per_1k) || 0;
            const outputPricePer1k = parseFloat(modelPricing.output_per_1k) || 0;

            const inputTokens = estimation.input_tokens || 0;
            const outputTokens = estimation.output_tokens || 0;

            const inputCost = (inputTokens / 1000.0) * inputPricePer1k;
            const outputCost = (outputTokens / 1000.0) * outputPricePer1k;

            return {
                pricing_available: true,
                total_cost: inputCost + outputCost,
                breakdown: {
                    input_cost: inputCost,
                    output_cost: outputCost
                },
                model: modelName
            };
        } catch (e) {
            console.warn('Error computing cost from pricing', e);
            return null;
        }
    }

    async function estimateTranslationTokens(useThinkingMode = false) {
        try {
            const response = await window.fetchWithCSRF('/api/translate/estimate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: koreanText,
                    novel_id: window.chapterData.novelId,
                    images: [],
                    use_thinking_mode: useThinkingMode
                })
            });

            const data = await response.json();

            if (data.success && data.estimation) {
                const est = data.estimation;
                const inputTokens = formatNumber(est.input_tokens || 0);
                const outputTokens = formatNumber(est.output_tokens || 0);
                const totalTokens = formatNumber(est.total_tokens || 0);

                let message = `Estimated Token Usage:\n\n` +
                    `Input: ~${inputTokens} tokens\n` +
                    `Output: ~${outputTokens} tokens\n` +
                    `Total: ~${totalTokens} tokens\n`;

                let costInfo = data.cost_info || null;
                if ((!costInfo || !costInfo.pricing_available) && window.chapterData && window.chapterData.translationModel) {
                    const local = await computeCostFromPricing(data.estimation, window.chapterData.translationModel || data.model || 'default');
                    if (local) costInfo = local;
                }

                if (costInfo && costInfo.pricing_available && costInfo.total_cost !== null) {
                    const cost = formatCost(costInfo.total_cost);
                    message += `\nEstimated Cost: ${cost}\n`;
                } else {
                    message += `\nUse these counts with your provider's pricing or set model values (Values button) to auto-calculate cost.\n`;
                }

                message += `\nProceed with translation?`;

                const confirmed = confirm(message);

                return confirmed ? est : null;
            } else {

                console.warn('Token estimation failed, proceeding anyway:', data.error);
                return true;
            }
        } catch (error) {
            console.error('Error estimating tokens:', error);

            return true;
        }
    }

    async function getEstimationOnly(useThinkingMode = false) {
        try {
            const response = await window.fetchWithCSRF('/api/translate/estimate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: koreanText, novel_id: window.chapterData.novelId, images: [], use_thinking_mode: useThinkingMode })
            });
            const data = await response.json();
            if (data && data.success && data.estimation) {
                return { estimation: data.estimation, cost_info: data.cost_info || null, model: data.model || window.chapterData.translationModel };
            }
            return null;
        } catch (e) {
            console.warn('Silent estimation failed', e);
            return null;
        }
    }

    async function fetchChapterTokenUsage(chapterId) {
        if (!chapterId) return;

        try {

            const settingsResp = await fetch('/api/settings');
            if (settingsResp.ok) {
                const settings = await settingsResp.json();
                if (settings.show_translation_cost === false) return;
            }

            const response = await fetch(`/api/chapter/${chapterId}/token-usage`);
            const data = await response.json();

            if (data.success && data.token_usage && data.token_usage.length > 0) {

                const latest = data.token_usage[0];
                updateTokenUsageDisplay({
                    input_tokens: latest.input_tokens,
                    output_tokens: latest.output_tokens,
                    total_tokens: latest.total_tokens
                }, latest.cost_info || null);
            }
        } catch (error) {
            console.error('Error fetching token usage:', error);
        }
    }

    function updateChapterTitle(newTranslatedTitle) {
        const titleElement = document.querySelector('.header-title h1');

        if (titleElement && newTranslatedTitle) {

            const thinkingBadge = titleElement.querySelector('.thinking-badge');
            const titleText = escapeHtml(newTranslatedTitle.trim());

            if (thinkingBadge) {
                titleElement.textContent = '';
                const textNode = document.createTextNode(titleText + ' ');
                titleElement.appendChild(textNode);
                titleElement.appendChild(thinkingBadge);
            } else {

                titleElement.textContent = titleText;
            }

            let originalTitleDiv = document.querySelector('.original-title');
            if (originalTitleDiv) {
                originalTitleDiv.textContent = 'Original: ' + chapterTitle;
            } else {

                const headerTitle = document.querySelector('.header-title');
                if (headerTitle) {
                    originalTitleDiv = document.createElement('div');
                    originalTitleDiv.className = 'original-title';
                    originalTitleDiv.textContent = 'Original: ' + chapterTitle;
                    headerTitle.appendChild(originalTitleDiv);
                }
            }
        } else {
            console.error('Cannot update title - element or title missing', { titleElement, newTranslatedTitle });
        }
    }

    if (isTranslated) {
        applyCharacterHighlights();
        if (translateBtn) translateBtn.textContent = '🔄 Re-translate';
        if (compareBtn) compareBtn.classList.remove('hidden');
        if (saveBtn) saveBtn.classList.add('hidden');
        if (editBtn) editBtn.classList.remove('hidden');

        if (thinkingIndicator && isThinkingModel(translationModel)) {
            thinkingIndicator.classList.remove('hidden');
            thinkingIndicator.title = `Translated with Thinking Mode (${translationModel})`;
        }
    }

    async function performTranslation(useThinkingMode = false) {
        const activeBtn = useThinkingMode ? thinkBtn : translateBtn;
        const otherBtn = useThinkingMode ? thinkBtn : translateBtn;

        if (!activeBtn) {
            console.error('Translate button not found');
            return;
        }

        activeBtn.disabled = true;
        if (otherBtn) otherBtn.disabled = true;

        const originalText = activeBtn.textContent;
        activeBtn.textContent = useThinkingMode ? '🧠 Thinking...' : '⏳ Translating...';

        if (saveBtn) saveBtn.classList.add('hidden');

        if (isCompareMode) {
            toggleCompareMode();
        }

        const statusDiv = document.getElementById('translation-status');

        try {

            const response = await window.fetchWithCSRF('/api/translate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: koreanText,
                    novel_id: window.chapterData.novelId,
                    chapter_id: window.chapterData.chapterId,
                    images: [],
                    use_thinking_mode: useThinkingMode
                })
            });

            const data = await response.json();

            if (data.success) {
                translatedText = data.translated_text;
                translationModel = data.model_used;

                if (data.token_usage) {

                    try {
                        const settingsResp = await fetch('/api/settings');
                        if (settingsResp.ok) {
                            const settings = await settingsResp.json();
                            if (settings.show_translation_cost !== false) {
                                updateTokenUsageDisplay(data.token_usage, data.cost_info);
                            }
                        } else {
                            updateTokenUsageDisplay(data.token_usage, data.cost_info);
                        }
                    } catch (e) {
                        updateTokenUsageDisplay(data.token_usage, data.cost_info);
                    }
                } else {

                    if (window.chapterData.chapterId) {
                        fetchChapterTokenUsage(window.chapterData.chapterId);
                    }
                }

                if (chapterTitle) {
                    try {
                        const titleResponse = await window.fetchWithCSRF('/api/translate', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                text: chapterTitle,
                                novel_id: window.chapterData.novelId,
                                chapter_id: window.chapterData.chapterId,
                                images: [],
                                use_thinking_mode: useThinkingMode
                            })
                        });

                        const titleData = await titleResponse.json();
                        if (titleData.success && titleData.translated_text) {
                            translatedTitle = titleData.translated_text;
                            updateChapterTitle(translatedTitle);
                        } else {
                            console.error('Title translation failed:', titleData.error || 'Unknown error');
                        }
                    } catch (titleError) {
                        console.error('Error translating title:', titleError);

                    }
                }

                isTranslated = true;

                if (singleView) singleView.classList.remove('hidden');
                if (sideView) sideView.classList.remove('active');
                if (editArea) editArea.classList.add('hidden');
                if (textDisplay) textDisplay.classList.remove('hidden');

                applyCharacterHighlights();

                if (translateBtn) translateBtn.textContent = '🔄 Re-translate';
                if (compareBtn) compareBtn.classList.remove('hidden');
                if (saveBtn) saveBtn.classList.remove('hidden');
                if (editBtn) editBtn.classList.remove('hidden');

                if (statusDiv) {
                    statusDiv.classList.remove('hidden');
                    statusDiv.style.display = 'flex';
                    statusDiv.innerHTML = '<span class="status-icon">✅</span><span class="status-text">Translation complete!</span>';
                    setTimeout(() => {
                        statusDiv.style.display = 'none';
                        statusDiv.classList.add('hidden');
                    }, 3000);
                }

                if (thinkingIndicator) {
                    if (useThinkingMode || isThinkingModel(translationModel)) {
                        thinkingIndicator.classList.remove('hidden');
                        thinkingIndicator.title = `Translated with Thinking Mode (${translationModel})`;
                    } else {
                        thinkingIndicator.classList.add('hidden');
                    }
                }

            } else {
                const errorDiv = document.createElement('div');
                errorDiv.style.cssText = 'color: #e53e3e; padding: 40px; text-align: center;';
                errorDiv.textContent = `❌ Error: ${data.error || 'Translation failed'}`;
                textDisplay.innerHTML = '';
                textDisplay.appendChild(errorDiv);
                if (statusDiv) {
                    statusDiv.style.display = 'none';
                }
            }
        } catch (error) {
            const errorDiv = document.createElement('div');
            errorDiv.style.cssText = 'color: #e53e3e; padding: 40px; text-align: center;';
            errorDiv.textContent = `❌ Error: ${error.message}`;
            textDisplay.innerHTML = '';
            textDisplay.appendChild(errorDiv);
            if (statusDiv) {
                statusDiv.style.display = 'none';
            }
        } finally {
            if (activeBtn) {
                activeBtn.disabled = false;
                activeBtn.textContent = originalText;
            }
            if (otherBtn) otherBtn.disabled = false;
            if (isTranslated && activeBtn) {
                activeBtn.textContent = '🔄 Re-translate';
            }
        }
    }

    if (translateBtn) {
        translateBtn.addEventListener('click', () => {
            performTranslation(false);
        });
    }

    if (thinkBtn) {
        thinkBtn.addEventListener('click', () => {
            performTranslation(true);
        });
    }

    function toggleCompareMode() {
        isCompareMode = !isCompareMode;
        const exitBtn = document.getElementById('exit-compare-btn');

        if (isCompareMode) {
            singleView.classList.add('hidden');
            sideView.classList.add('active');
            if (exitBtn) exitBtn.classList.remove('hidden');

            prepareComparisonView();
        } else {
            singleView.classList.remove('hidden');
            sideView.classList.remove('active');
            if (exitBtn) exitBtn.classList.add('hidden');

            if (isTranslated) {
                applyCharacterHighlights();
            } else {
                textDisplay.textContent = koreanText;
            }
        }
    }

    function prepareComparisonView() {

        let kText = (window.chapterData && window.chapterData.koreanText) || koreanText || '';
        let tText = (window.chapterData && window.chapterData.translatedText) || translatedText || '';

        if (!tText && isTranslated && textDisplay) {
            tText = textDisplay.textContent;
        }

        let koreanContent = '';
        if (window.chapterData && window.chapterData.images && window.chapterData.images.length > 0) {
            koreanContent += '<div style="margin-bottom: 20px; text-align: center;">';
            window.chapterData.images.forEach(img => {
                const escapedPath = escapeHtml(img.local_path);
                const escapedAlt = escapeHtml(img.alt || 'Chapter Image');
                koreanContent += `<div style="margin-bottom: 15px;"><img src="/images/${escapedPath}" alt="${escapedAlt}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"></div>`;
            });
            koreanContent += '</div>';
        }
        koreanContent += escapeHtml(kText);

        let englishContent = '';
        if (window.chapterData && window.chapterData.images && window.chapterData.images.length > 0) {
            englishContent += '<div style="margin-bottom: 20px; text-align: center;">';
            window.chapterData.images.forEach(img => {
                const escapedPath = escapeHtml(img.local_path);
                const escapedAlt = escapeHtml(img.alt || 'Chapter Image');
                englishContent += `<div style="margin-bottom: 15px;"><img src="/images/${escapedPath}" alt="${escapedAlt}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"></div>`;
            });
            englishContent += '</div>';
        }
        englishContent += escapeHtml(tText);

        if (koreanPanel) koreanPanel.innerHTML = koreanContent;
        if (englishPanel) englishPanel.innerHTML = englishContent;
    }

    const exitBtn = document.getElementById('exit-compare-btn');
    if (exitBtn) {
        exitBtn.addEventListener('click', () => {
            toggleCompareMode();

            const url = new URL(window.location);
            url.searchParams.delete('compare');
            window.history.replaceState({}, '', url);
        });
    }

    if (window.chapterData) {
        koreanText = window.chapterData.koreanText || koreanText || '';
        translatedText = window.chapterData.translatedText || translatedText || '';
        isTranslated = translatedText && translatedText.trim().length > 0;
    }

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('compare') === 'true' && isTranslated) {
        toggleCompareMode();
    }

    if (editBtn) {
        editBtn.addEventListener('click', () => {
            if (isCompareMode) toggleCompareMode();
            if (textDisplay) textDisplay.classList.add('hidden');
            if (editArea) editArea.classList.remove('hidden');
            if (editTextarea) {
                editTextarea.value = translatedText;
                editTextarea.focus();

                editTextarea.setSelectionRange(0, 0);
                editTextarea.scrollTop = 0;
            }
        });
    }

    if (saveEditBtn) {
        saveEditBtn.addEventListener('click', async () => {
            const newText = editTextarea.value.trim();
            if (!newText) return window.showAlertModal('Error', 'Text cannot be empty.', 'error');

            translatedText = newText;
            textDisplay.textContent = translatedText;
            textDisplay.classList.remove('hidden');
            editArea.classList.add('hidden');

            try {
                const response = await window.fetchWithCSRF('/api/save-translation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        novel_id: window.chapterData.novelId,
                        chapter_index: window.chapterData.chapterIndex,
                        translated_text: translatedText,
                        translated_title: translatedTitle || undefined
                    })
                });
                const data = await response.json();
                if (!data.success) window.showAlertModal('Save Failed', data.error || 'Unknown error', 'error');
            } catch (error) {
                window.showAlertModal('Save Error', error.message, 'error');
            }
        });
    }

    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', () => {
            if (textDisplay) textDisplay.classList.remove('hidden');
            if (editArea) editArea.classList.add('hidden');
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            saveBtn.disabled = true;
            saveBtn.textContent = '💾 Saving...';

            try {
                const response = await window.fetchWithCSRF('/api/save-translation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        novel_id: window.chapterData.novelId,
                        chapter_index: window.chapterData.chapterIndex,
                        translated_text: translatedText,
                        translated_title: translatedTitle || undefined
                    })
                });

                const data = await response.json();

                if (data.success) {
                    saveBtn.textContent = '✓ Saved!';
                    setTimeout(() => {
                        saveBtn.textContent = '💾 Save Translation';
                        saveBtn.disabled = false;
                        saveBtn.classList.add('hidden');
                    }, 2000);
                } else {
                    window.showAlertModal('Error', data.error || 'Save failed', 'error');
                    saveBtn.textContent = '💾 Save Translation';
                    saveBtn.disabled = false;
                }
            } catch (error) {
                window.showAlertModal('Error', error.message, 'error');
                saveBtn.textContent = '💾 Save Translation';
                saveBtn.disabled = false;
            }
        });
    }

    document.addEventListener('keydown', (e) => {

        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        if (e.ctrlKey || e.altKey || e.metaKey) {
            return;
        }

        switch (e.key.toLowerCase()) {
            case 't':

                e.preventDefault();
                if (!translateBtn.disabled) {
                    translateBtn.click();
                }
                break;

            case 'e':

                e.preventDefault();
                if (!editBtn.classList.contains('hidden') && !editBtn.disabled) {
                    editBtn.click();
                }
                break;

            case 's':

                e.preventDefault();
                if (!saveBtn.classList.contains('hidden') && !saveBtn.disabled) {
                    saveBtn.click();
                }
                break;

            case 'c':

                e.preventDefault();
                if (!compareBtn.classList.contains('hidden') && !compareBtn.disabled) {
                    compareBtn.click();
                }
                break;

            case 'escape':

                e.preventDefault();
                if (!editArea.classList.contains('hidden')) {

                    cancelEditBtn.click();
                } else if (isCompareMode) {

                    compareBtn.click();
                }
                break;

            case '?':

                e.preventDefault();
                toggleShortcutsHelp();
                break;
        }
    });

    function toggleShortcutsHelp() {
        const modal = document.getElementById('shortcuts-modal');
        if (modal) {
            modal.style.display = modal.style.display === 'flex' ? 'none' : 'flex';
        }
    }

    document.addEventListener('click', (e) => {
        const modal = document.getElementById('shortcuts-modal');
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('shortcuts-modal');
            if (modal && modal.style.display === 'flex') {
                e.preventDefault();
                modal.style.display = 'none';
            }

            const charPopup = document.getElementById('character-popup');
            if (charPopup && charPopup.style.display === 'flex') {
                e.preventDefault();
                charPopup.style.display = 'none';
            }
        }
    });

    if (isTranslated && !isCompareMode) {
        applyCharacterHighlights();
    }

    function applyCharacterHighlights() {
        if (!textDisplay) return;
        if (!window.chapterData.glossary || Object.keys(window.chapterData.glossary).length === 0) {
            textDisplay.textContent = translatedText;
            return;
        }

        const highlightedText = highlightCharacters(translatedText);
        textDisplay.innerHTML = highlightedText;

        addCharacterClickHandlers();
    }

    function highlightCharacters(text) {
        if (!text) return '';

        let processedText = escapeHtml(text);
        const glossary = window.chapterData.glossary;

        const charsWithDescriptions = Object.keys(glossary).filter(charId => {
            const charInfo = glossary[charId];
            return charInfo.description && charInfo.description.trim();
        });

        const sortedCharIds = charsWithDescriptions.sort((a, b) => {
            const nameA = glossary[a].english_name || '';
            const nameB = glossary[b].english_name || '';
            return nameB.length - nameA.length;
        });

        const placeholders = {};
        let placeholderCounter = 0;

        sortedCharIds.forEach(charId => {
            const charInfo = glossary[charId];
            const englishName = charInfo.english_name;

            if (englishName && englishName.trim().length > 0) {
                const escapedName = escapeHtml(englishName);
                const regex = new RegExp(`\\b${escapeRegExp(englishName)}\\b`, 'gi');

                processedText = processedText.replace(regex, (match) => {
                    const placeholder = `__CHAR_PLACEHOLDER_${placeholderCounter++}__`;
                    const escapedMatch = escapeHtml(match);
                    const escapedCharId = escapeHtml(charId);
                    placeholders[placeholder] = `<span class="character-highlight has-description" data-char-id="${escapedCharId}">${escapedMatch}</span>`;
                    return placeholder;
                });
            }
        });

        Object.keys(placeholders).forEach(placeholder => {
            processedText = processedText.replace(placeholder, placeholders[placeholder]);
        });

        return processedText;
    }

    function escapeRegExp(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function addCharacterClickHandlers() {
        const highlights = textDisplay.querySelectorAll('.character-highlight');
        highlights.forEach(span => {
            const charId = span.getAttribute('data-char-id');
            const glossary = window.chapterData.glossary;
            const charInfo = glossary[charId];

            if (charInfo && charInfo.description && charInfo.description.trim()) {
                span.classList.add('has-description');
                span.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showCharacterPopup(charId);
                });
            } else {

                span.style.cursor = 'default';
            }
        });
    }

    function showCharacterPopup(charId) {
        const glossary = window.chapterData.glossary;
        const charInfo = glossary[charId];

        if (!charInfo) return;

        if (!charInfo.description || !charInfo.description.trim()) {
            return;
        }

        const popup = document.getElementById('character-popup');
        const nameEl = document.getElementById('popup-name');
        const metaEl = document.getElementById('popup-meta');
        const descEl = document.getElementById('popup-description');

        nameEl.textContent = charInfo.english_name || charInfo.korean_name;

        let metaHtml = `<span class="popup-korean">${charInfo.korean_name || ''}</span>`;

        if (charInfo.gender && charInfo.gender !== 'auto') {
            let genderLabel = charInfo.gender;
            if (charInfo.gender === 'male') genderLabel = 'Male (he/him)';
            if (charInfo.gender === 'female') genderLabel = 'Female (she/her)';
            if (charInfo.gender === 'other') genderLabel = 'Other (they/them)';

            metaHtml += `<span class="popup-gender gender-${charInfo.gender}">${genderLabel}</span>`;
        }
        metaEl.innerHTML = metaHtml;

        const description = charInfo.description;
        descEl.innerHTML = parseMarkdown(description);

        popup.style.display = 'flex';
    }

    const closePopupBtn = document.querySelector('.close-popup-btn');
    if (closePopupBtn) {
        closePopupBtn.addEventListener('click', () => {
            document.getElementById('character-popup').style.display = 'none';
        });
    }

    const charPopup = document.getElementById('character-popup');
    if (charPopup) {
        charPopup.addEventListener('click', (e) => {
            if (e.target === charPopup) {
                charPopup.style.display = 'none';
            }
        });
    }

    function parseMarkdown(text) {
        if (!text) return '';

        let html = text

            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')

            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

            .replace(/\*(.*?)\*/g, '<em>$1</em>')

            .replace(/^- (.*$)/gm, '<li>$1</li>')

            .replace(/\n/g, '<br>');

        if (html.includes('<li>')) {
            html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        }

        return html;
    }

    const originalTranslateBtnClick = translateBtn.onclick;

    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList' && mutation.target === textDisplay) {

                if (!textDisplay.querySelector('.character-highlight') &&
                    window.chapterData.glossary &&
                    Object.keys(window.chapterData.glossary).length > 0 &&
                    textDisplay.textContent.trim().length > 0 &&
                    !isCompareMode) {

                    observer.disconnect();
                    applyCharacterHighlights();

                    observer.observe(textDisplay, { childList: true });
                }
            }
        });
    });

    observer.observe(textDisplay, { childList: true });

    if (window.chapterData.chapterId) {
        fetchChapterTokenUsage(window.chapterData.chapterId);
    }

    (function checkTranslationStatus() {
        const chapterId = window.chapterData.chapterId;
        const hasTranslation = isTranslated;

        if (chapterId && !hasTranslation) {

            fetch(`/api/check-chapter-translation?novel_id=${encodeURIComponent(window.chapterData.novelId)}&chapter_index=${window.chapterData.chapterIndex}`)
                .then(response => response.json())
                .then(data => {

                    const activeStatuses = ['in_progress', 'queued', 'processing'];
                    const isActive = activeStatuses.includes(data.translation_status);

                    if (isActive) {
                        const statusDiv = document.getElementById('translation-status');
                        if (statusDiv) {
                            statusDiv.classList.remove('hidden');
                            statusDiv.style.display = 'flex';

                            const statusText = statusDiv.querySelector('.status-text');
                            if (statusText) {
                                statusText.textContent = data.translation_status === 'queued' ? 'Translation queued...' : 'Chapter translating...';
                            }

                            let pollCount = 0;
                            const maxPolls = 100;

                            const pollInterval = setInterval(async () => {
                                pollCount++;

                                try {
                                    const response = await fetch(`/api/check-chapter-translation?novel_id=${encodeURIComponent(window.chapterData.novelId)}&chapter_index=${window.chapterData.chapterIndex}`);
                                    if (response.ok) {
                                        const pollData = await response.json();

                                        const hasContent = pollData.translated_content || pollData.translated_text;
                                        const isComplete = pollData.translated && hasContent;

                                        if (isComplete) {
                                            clearInterval(pollInterval);

                                            statusDiv.innerHTML = '<span class="status-icon">✅</span><span class="status-text">Translation complete! Refreshing...</span>';

                                            setTimeout(() => {
                                                window.location.reload();
                                            }, 1000);
                                            return;
                                        }

                                        if (!activeStatuses.includes(pollData.translation_status) && !pollData.translated) {
                                            clearInterval(pollInterval);
                                            statusDiv.innerHTML = '<span class="status-icon">❌</span><span class="status-text">Translation failed or stopped.</span>';
                                            return;
                                        }
                                    }
                                } catch (error) {
                                    console.error('Error checking translation status:', error);
                                }

                                if (pollCount >= maxPolls) {
                                    clearInterval(pollInterval);
                                    statusDiv.innerHTML = '<span class="status-icon">⚠️</span><span class="status-text">Translation taking longer than expected. Please refresh manually.</span>';
                                }
                            }, 3000);
                        }
                    }
                })
                .catch(error => {
                    console.error('Error checking initial translation status:', error);
                });
        }
    })();

});
