import os
from models.novel import get_display_title

DATA_DIR = 'data'

def get_user_exports_dir(user_id):

    exports_dir = os.path.join(DATA_DIR, 'users', user_id, 'exports')
    os.makedirs(exports_dir, exist_ok=True)
    return exports_dir

def get_user_images_dir(user_id):

    return os.path.join(DATA_DIR, 'users', user_id, 'images')

def export_to_epub(novel_id, novel, user_id):

    try:
        from ebooklib import epub
        
        book = epub.EpubBook()
        
        title = get_display_title(novel)
        book.set_identifier(f'novel_{novel_id}')
        book.set_title(title)
        book.set_language('en')
        
        epub_chapters = []
        for idx, chapter in enumerate(novel.get('chapters', [])):
            if chapter is None:
                continue
                
            content = chapter.get('translated_text') or chapter.get('korean_text', '')
            chapter_title = chapter.get('translated_title') or chapter.get('title', f'Chapter {idx + 1}')
            
            c = epub.EpubHtml(title=chapter_title,
                            file_name=f'chap_{idx + 1}.xhtml',
                            lang='en')
            
            html_content = f'<h1>{chapter_title}</h1>'
            
            if chapter.get('images'):
                for img in chapter['images']:
                    img_path = os.path.join(get_user_images_dir(user_id), img['local_path'])
                    if os.path.exists(img_path):
                        try:
                            with open(img_path, 'rb') as f:
                                img_data = f.read()
                            epub_img = epub.EpubItem(
                                uid=f"img_{img['local_path']}",
                                file_name=f"images/{img['local_path']}",
                                media_type='image/jpeg',
                                content=img_data
                            )
                            book.add_item(epub_img)
                            html_content += f'<img src="images/{img["local_path"]}" alt="{img.get("alt", "Chapter Image")}"/><br/>'
                        except Exception as e:
                            pass                                
            
            paragraphs = content.split('\n')
            for para in paragraphs:
                if para.strip():
                    html_content += f'<p>{para}</p>'
            
            c.content = html_content
            book.add_item(c)
            epub_chapters.append(c)
        
        book.toc = epub_chapters
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ['nav'] + epub_chapters
        
        exports_dir = get_user_exports_dir(user_id)
        output_path = os.path.join(exports_dir, f'{novel_id}.epub')
        epub.write_epub(output_path, book)
        
        return output_path
    except ImportError:
        return None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

def export_to_pdf(novel_id, novel, user_id):

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        
        exports_dir = get_user_exports_dir(user_id)
        output_path = os.path.join(exports_dir, f'{novel_id}.pdf')
        
        doc = SimpleDocTemplate(output_path, pagesize=letter,
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        story = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='darkblue',
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        title = get_display_title(novel)
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.5*inch))
        story.append(PageBreak())
        
        chapter_style = ParagraphStyle(
            'ChapterTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor='darkblue',
            spaceAfter=20
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=12,
            leading=18,
            alignment=TA_JUSTIFY
        )
        
        for idx, chapter in enumerate(novel.get('chapters', [])):
            if chapter is None:
                continue
                
            chapter_title = chapter.get('translated_title') or chapter.get('title', f'Chapter {idx + 1}')
            story.append(Paragraph(f"Chapter {idx + 1}: {chapter_title}", chapter_style))
            story.append(Spacer(1, 0.2*inch))
            
            if chapter.get('images'):
                for img in chapter['images']:
                    img_path = os.path.join(get_user_images_dir(user_id), img['local_path'])
                    if os.path.exists(img_path):
                        try:
                            img_obj = Image(img_path, width=4*inch, height=3*inch, kind='proportional')
                            story.append(img_obj)
                            story.append(Spacer(1, 0.2*inch))
                        except Exception as e:
                            pass                                
            
            content = chapter.get('translated_text') or chapter.get('korean_text', '')
            paragraphs = content.split('\n')
            
            for para in paragraphs:
                if para.strip():
                    story.append(Paragraph(para, body_style))
                    story.append(Spacer(1, 0.1*inch))
            
            story.append(PageBreak())
        
        doc.build(story)
        return output_path
        
    except ImportError:
        return None
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None