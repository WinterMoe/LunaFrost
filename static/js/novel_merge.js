
let mergeState = {
    sourceNovelId: null,
    targetNovelId: null,
    previewData: null,
    metadataChoices: {},
    chapterChoices: {}
};

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function showMergeModal() {
    const modal = document.getElementById('merge-modal');
    if (!modal) return;

    mergeState.sourceNovelId = window.novelSettingsData.novelId;
    mergeState.targetNovelId = null;
    mergeState.previewData = null;
    mergeState.metadataChoices = {};
    mergeState.chapterChoices = {};

    try {
        const response = await fetch('/');
        const html = await response.text();

        showNovelSelectionStep();
        modal.style.display = 'flex';
    } catch (error) {
        console.error('Error loading novels:', error);
        window.showAlertModal('Error', 'Failed to load novels list', 'error');
    }
}

async function showNovelSelectionStep() {
    const modalContent = document.getElementById('merge-modal-content');

    modalContent.innerHTML = `
        <div style="padding: 20px; text-align: center;">
            <div class="spinner"></div>
            <p>Loading novels...</p>
        </div>
    `;

    try {

        const response = await fetch('/');
        const html = await response.text();

        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const novelLinks = doc.querySelectorAll('.novel-card-link');

        const novels = [];
        novelLinks.forEach(link => {
            const href = link.getAttribute('href');
            const match = href.match(/\/novel\/([^\/]+)/);
            if (match) {
                const novelId = match[1];

                if (novelId !== mergeState.sourceNovelId) {

                    const titleElement = link.querySelector('h2');
                    const title = titleElement ? titleElement.textContent.trim() : novelId;
                    novels.push({ id: novelId, title: title });
                }
            }
        });

        let modalHtml = `
            <div style="padding: 20px;">
                <h2 style="margin-bottom: 20px;">Select Novel to Merge</h2>
                <p style="color: var(--text-secondary); margin-bottom: 15px;">
                    Click on a novel to merge it with the current one.
                </p>
                <div style="margin-bottom: 15px;">
                    <input type="text" id="novel-search-input" placeholder="🔍 Search novels..." 
                           style="width: 100%; padding: 10px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-secondary); color: var(--text-primary);">
                </div>
        `;

        if (novels.length > 0) {
            modalHtml += '<div id="novel-list-container" style="max-height: 400px; overflow-y: auto; margin-bottom: 20px;">';
            novels.forEach(novel => {
                const escapedTitle = escapeHtml(novel.title);
                const escapedId = escapeHtml(novel.id);
                modalHtml += `
                    <div class="novel-select-item" data-novel-id="${escapedId}" data-novel-title="${escapedTitle.toLowerCase()}"
                         style="padding: 12px; margin-bottom: 8px; background: var(--bg-secondary); border-radius: 6px; cursor: pointer; border: 2px solid transparent; transition: all 0.2s;">
                        <div style="font-weight: 600;">${escapedTitle}</div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px;">ID: ${escapedId}</div>
                    </div>
                `;
            });
            modalHtml += '</div>';
        } else {
            modalHtml += `
                <div style="background: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    No other novels found to merge with.
                </div>
            `;
        }

        modalHtml += `
                <div style="display: flex; gap: 10px;">
                    <button id="cancel-merge-btn" class="btn btn-secondary" style="flex: 1;">Cancel</button>
                </div>
            </div>
        `;

        modalContent.innerHTML = modalHtml;

        const searchInput = document.getElementById('novel-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.toLowerCase();
                document.querySelectorAll('.novel-select-item').forEach(item => {
                    const title = item.getAttribute('data-novel-title');
                    const id = item.getAttribute('data-novel-id').toLowerCase();
                    if (title.includes(query) || id.includes(query)) {
                        item.style.display = 'block';
                    } else {
                        item.style.display = 'none';
                    }
                });
            });

            setTimeout(() => searchInput.focus(), 100);
        }

        document.querySelectorAll('.novel-select-item').forEach(item => {
            item.addEventListener('click', function () {

                document.querySelectorAll('.novel-select-item').forEach(i => {
                    i.style.borderColor = 'transparent';
                    i.style.background = 'var(--bg-secondary)';
                });

                this.style.borderColor = 'var(--primary-color)';
                this.style.background = 'var(--bg-primary)';

                const novelId = this.getAttribute('data-novel-id');
                loadMergePreview(novelId);
            });

            item.addEventListener('mouseenter', function () {
                if (this.style.borderColor !== 'var(--primary-color)') {
                    this.style.background = 'var(--bg-primary)';
                }
            });
            item.addEventListener('mouseleave', function () {
                if (this.style.borderColor !== 'var(--primary-color)') {
                    this.style.background = 'var(--bg-secondary)';
                }
            });
        });

        document.getElementById('cancel-merge-btn').addEventListener('click', closeMergeModal);

    } catch (error) {
        console.error('Error loading novels:', error);
        modalContent.innerHTML = `
            <div style="padding: 20px;">
                <h2 style="margin-bottom: 20px; color: #721c24;">Error</h2>
                <p style="color: #721c24; margin-bottom: 20px;">Failed to load novels list.</p>
                <button id="cancel-merge-btn" class="btn btn-secondary">Close</button>
            </div>
        `;
        document.getElementById('cancel-merge-btn').addEventListener('click', closeMergeModal);
    }
}

async function loadMergePreview(targetNovelId) {
    if (!targetNovelId) {
        window.showAlertModal('Error', 'Please select a novel', 'error');
        return;
    }

    mergeState.targetNovelId = targetNovelId;

    const modalContent = document.getElementById('merge-modal-content');
    modalContent.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="spinner"></div><p>Analyzing novels...</p></div>';

    try {
        const response = await window.fetchWithCSRF(`/api/novel/${encodeURIComponent(mergeState.sourceNovelId)}/merge/preview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_novel_id: targetNovelId })
        });

        const data = await response.json();

        if (data.success) {
            mergeState.previewData = data.preview;
            showMergePreview(data.preview);
        } else {
            throw new Error(data.error || 'Failed to preview merge');
        }
    } catch (error) {
        console.error('Error previewing merge:', error);
        window.showAlertModal('Error', error.message, 'error');
        showNovelSelectionStep();
    }
}

function showMergePreview(preview) {
    const hasMetadataConflicts = Object.keys(preview.metadata_conflicts).length > 0;
    const hasChapterConflicts = preview.chapter_conflicts.length > 0;

    let html = `
        <div style="padding: 20px; max-height: 70vh; overflow-y: auto;">
            <h2 style="margin-bottom: 10px;">Merge Preview</h2>
            <p style="color: var(--text-secondary); margin-bottom: 20px;">
                Merging <strong>${escapeHtml(preview.source_novel.title)}</strong> (${preview.source_novel.chapter_count} chapters) 
                with <strong>${escapeHtml(preview.target_novel.title)}</strong> (${preview.target_novel.chapter_count} chapters)
            </p>
            
            <div style="background: var(--bg-secondary); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 10px 0; font-size: 1rem;">📊 Merge Summary</h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>Total chapters after merge: <strong>${preview.total_after_merge}</strong></li>
                    <li>Unique chapters from source: <strong>${preview.unique_source_chapters.length}</strong></li>
                    <li>Unique chapters from target: <strong>${preview.unique_target_chapters.length}</strong></li>
                    <li>Conflicting chapters: <strong>${preview.chapter_conflicts.length}</strong></li>
                </ul>
            </div>
    `;

    if (hasMetadataConflicts) {
        html += '<h3 style="margin: 20px 0 10px 0;">⚠️ Metadata Conflicts</h3>';
        html += '<p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 15px;">Choose which values to keep:</p>';

        for (const [field, values] of Object.entries(preview.metadata_conflicts)) {

            if (field === 'tags' || field === 'translated_tags' || field === 'synopsis' || field === 'translated_synopsis') continue;

            if (field === 'title') {

                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--bg-secondary); border-radius: 6px;">
                        <label style="font-weight: 600; display: block; margin-bottom: 8px;">Title:</label>
                        <div style="display: flex; gap: 10px;">
                            <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                                <input type="radio" name="metadata_title" value="source" checked>
                                <div style="margin-left: 5px; font-size: 0.9rem;">
                                    <div><strong>Source</strong></div>
                                    <div style="margin-top: 4px; color: var(--text-secondary); font-size: 0.85rem;">
                                        ${values.source.original_title ? `<div>🇰🇷 Original: ${escapeHtml(values.source.original_title)}</ div>` : ''}
                                        ${values.source.translated_title ? `<div>🇺🇸 Translated: ${escapeHtml(values.source.translated_title)}</div>` : ''}
                                    </div>
                                </div>
                            </label>
                            <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                                <input type="radio" name="metadata_title" value="target">
                                <div style="margin-left: 5px; font-size: 0.9rem;">
                                    <div><strong>Target</strong></div>
                                    <div style="margin-top: 4px; color: var(--text-secondary); font-size: 0.85rem;">
                                        ${values.target.original_title ? `<div>🇰🇷 Original: ${escapeHtml(values.target.original_title)}</div>` : ''}
                                        ${values.target.translated_title ? `<div>🇺🇸 Translated: ${escapeHtml(values.target.translated_title)}</div>` : ''}
                                    </div>
                                </div>
                            </label>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 8px; margin-bottom: 0;">
                            💡 Both Korean and translated titles will be preserved
                        </p>
                    </div>
                `;
            } else if (field === 'author') {

                html += `
                    <div style="margin-bottom: 15px; padding: 12px; background: var(--bg-secondary); border-radius: 6px;">
                        <label style="font-weight: 600; display: block; margin-bottom: 8px;">Author:</label>
                        <div style="display: flex; gap: 10px;">
                            <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                                <input type="radio" name="metadata_author" value="source" checked>
                                <div style="margin-left: 5px; font-size: 0.9rem;">
                                    <div><strong>Source</strong></div>
                                    <div style="margin-top: 4px; color: var(--text-secondary); font-size: 0.85rem;">
                                        ${values.source.author ? `<div>🇰🇷 Original: ${values.source.author}</div>` : ''}
                                        ${values.source.translated_author ? `<div>🇺🇸 Translated: ${values.source.translated_author}</div>` : ''}
                                    </div>
                                </div>
                            </label>
                            <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                                <input type="radio" name="metadata_author" value="target">
                                <div style="margin-left: 5px; font-size: 0.9rem;">
                                    <div><strong>Target</strong></div>
                                    <div style="margin-top: 4px; color: var(--text-secondary); font-size: 0.85rem;">
                                        ${values.target.author ? `<div>🇰🇷 Original: ${values.target.author}</div>` : ''}
                                        ${values.target.translated_author ? `<div>🇺🇸 Translated: ${values.target.translated_author}</div>` : ''}
                                    </div>
                                </div>
                            </label>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 8px; margin-bottom: 0;">
                            💡 Both Korean and translated names will be preserved
                        </p>
                    </div>
                `;
            }
        }
    }

    if (hasChapterConflicts) {
        html += '<h3 style="margin: 20px 0 10px 0;">📚 Chapter Conflicts</h3>';
        html += '<p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 15px;">Both novels have these chapters. Choose which version to keep:</p>';

        for (const conflict of preview.chapter_conflicts) {
            html += `
                <div style="margin-bottom: 15px; padding: 12px; background: var(--bg-secondary); border-radius: 6px;">
                    <label style="font-weight: 600; display: block; margin-bottom: 8px;">Chapter ${conflict.chapter_number}:</label>
                    <div style="display: flex; gap: 10px;">
                        <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                            <input type="radio" name="chapter_${conflict.chapter_number}" value="source" checked>
                            <div style="margin-left: 20px; font-size: 0.85rem;">
                                <div><strong>${escapeHtml(conflict.source.translated_title || conflict.source.title)}</strong></div>
                                <div style="color: var(--text-secondary);">
                                    ${conflict.source.has_translation ? '✓ Translated' : '⏳ Not translated'} • 
                                    ${conflict.source.created_at ? escapeHtml(new Date(conflict.source.created_at).toLocaleDateString()) : 'Unknown date'}
                                </div>
                            </div>
                        </label>
                        <label style="flex: 1; cursor: pointer; padding: 8px; border: 1px solid var(--border-light); border-radius: 4px;">
                            <input type="radio" name="chapter_${conflict.chapter_number}" value="target">
                            <div style="margin-left: 20px; font-size: 0.85rem;">
                                <div><strong>${escapeHtml(conflict.target.translated_title || conflict.target.title)}</strong></div>
                                <div style="color: var(--text-secondary);">
                                    ${conflict.target.has_translation ? '✓ Translated' : '⏳ Not translated'} • 
                                    ${conflict.target.created_at ? escapeHtml(new Date(conflict.target.created_at).toLocaleDateString()) : 'Unknown date'}
                                </div>
                            </div>
                        </label>
                    </div>
                </div>
            `;
        }
    }

    if (!hasMetadataConflicts && !hasChapterConflicts) {
        html += `
            <div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0;">
                ✓ No conflicts detected! The novels can be merged automatically.
            </div>
        `;
    }

    html += `
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button id="cancel-merge-btn" class="btn btn-secondary" style="flex: 1;">Cancel</button>
                <button id="execute-merge-btn" class="btn btn-success" style="flex: 2;">🔀 Merge Novels</button>
            </div>
        </div>
    `;

    const modalContent = document.getElementById('merge-modal-content');
    modalContent.innerHTML = html;

    document.getElementById('cancel-merge-btn').addEventListener('click', closeMergeModal);
    document.getElementById('execute-merge-btn').addEventListener('click', executeMerge);
}

async function executeMerge() {
    console.log('Execute merge clicked');

    const metadataChoices = {};
    const chapterChoices = {};

    document.querySelectorAll('[name^="metadata_"]').forEach(radio => {
        if (radio.checked) {
            const field = radio.name.replace('metadata_', '');
            metadataChoices[field] = radio.value;
        }
    });

    document.querySelectorAll('[name^="chapter_"]').forEach(radio => {
        if (radio.checked) {
            const chNum = radio.name.replace('chapter_', '');
            chapterChoices[chNum] = radio.value;
        }
    });

    console.log('Choices collected:', { metadataChoices, chapterChoices });

    const confirmed = confirm('Are you sure you want to merge these novels?\n\nThis will combine all chapters and delete the target novel. This action cannot be undone!');

    if (!confirmed) {
        console.log('Merge cancelled');
        return;
    }

    console.log('Merge confirmed, sending request...');

    const modalContent = document.getElementById('merge-modal-content');
    modalContent.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="spinner"></div><p>Merging novels...</p></div>';

    try {
        const response = await window.fetchWithCSRF(`/api/novel/${encodeURIComponent(mergeState.sourceNovelId)}/merge/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target_novel_id: mergeState.targetNovelId,
                metadata_choices: metadataChoices,
                chapter_choices: chapterChoices
            })
        });

        const data = await response.json();

        if (data.success) {
            closeMergeModal();
            window.showAlertModal('Success', `Novels merged successfully! Total chapters: ${data.total_chapters}`, 'success');
            setTimeout(() => {
                window.location.href = `/novel/${encodeURIComponent(data.merged_novel_id)}`;
            }, 1500);
        } else {
            throw new Error(data.error || 'Failed to merge novels');
        }
    } catch (error) {
        console.error('Error merging novels:', error);
        window.showAlertModal('Error', error.message, 'error');
        closeMergeModal();
    }
}

function closeMergeModal() {
    const modal = document.getElementById('merge-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const mergeBtn = document.getElementById('merge-novels-btn');
    if (mergeBtn) {
        mergeBtn.addEventListener('click', showMergeModal);
    }
});
