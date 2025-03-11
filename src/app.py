# PYTHONPATH=. streamlit run src/app.py
# src/app.py
import streamlit as st
from src.database import get_db, SessionLocal
from src.models import Tree, TreeUpdate, Photo, Reminder, Species, Settings
from sqlalchemy import func, desc, and_, create_engine
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
import os
import pandas as pd
from PIL import Image
import PIL.ExifTags
import glob
import shutil
import json
from zipfile import ZipFile
from streamlit_extras.bottom_container import bottom
from streamlit_extras.stateful_button import button as state_button
from streamlit_extras.stylable_container import stylable_container
from streamlit_extras.grid import grid
import plotly.express as px
import tempfile

def export_bonsai_data(db, export_dir="exports"):
    """
    Export all bonsai data and images to a structured directory
    
    Parameters:
    db (SessionLocal): Database session
    export_dir (str): Base directory for exports
    
    Returns:
    str: Path to the created zip file
    """
    # Create timestamp for unique export
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = os.path.join(export_dir, f"bonsai_export_{timestamp}")
    os.makedirs(export_path, exist_ok=True)
    
    # Create images directory
    images_path = os.path.join(export_path, "images")
    os.makedirs(images_path, exist_ok=True)
    
    # Export tree data
    trees_data = []
    for tree in db.query(Tree).all():
        tree_data = {
            "tree_number": tree.tree_number,
            "tree_name": tree.tree_name,
            "species": tree.species_info.name,
            "date_acquired": tree.date_acquired.isoformat(),
            "origin_date": tree.origin_date.isoformat(),
            "current_girth": tree.current_girth,
            "notes": tree.notes,
            "is_archived": tree.is_archived,
            "training_age": tree.training_age,
            "true_age": tree.true_age,
            
            # Include related data
            "updates": [{
                "date": update.update_date.isoformat(),
                "girth": update.girth,
                "work_performed": update.work_performed
            } for update in tree.updates],
            
            "photos": [{
                "file_name": os.path.basename(photo.file_path),
                "photo_date": photo.photo_date.isoformat(),
                "description": photo.description,
                "is_starred": photo.is_starred
            } for photo in tree.photos],
            
            "reminders": [{
                "date": reminder.reminder_date.isoformat(),
                "message": reminder.message,
                "is_completed": reminder.is_completed
            } for reminder in tree.reminders]
        }
        trees_data.append(tree_data)
        
        # Copy tree images
        tree_images_path = os.path.join(images_path, tree.tree_number)
        os.makedirs(tree_images_path, exist_ok=True)
        
        for photo in tree.photos:
            if os.path.exists(photo.file_path):
                # Create filename with photo date
                photo_date = photo.photo_date.strftime("%Y%m%d")
                file_ext = os.path.splitext(photo.file_path)[1]
                new_filename = f"{photo_date}{file_ext}"
                
                # Copy image to export directory
                shutil.copy2(
                    photo.file_path,
                    os.path.join(tree_images_path, new_filename)
                )
    
    # Save JSON data
    with open(os.path.join(export_path, "trees_data.json"), 'w', encoding='utf-8') as f:
        json.dump(trees_data, f, indent=2, ensure_ascii=False)
    
    # Create Excel export with multiple sheets
    with pd.ExcelWriter(os.path.join(export_path, "bonsai_collection.xlsx")) as writer:
        # Trees overview
        trees_df = pd.DataFrame([{
            "Tree Number": t["tree_number"],
            "Name": t["tree_name"],
            "Species": t["species"],
            "Date Acquired": t["date_acquired"],
            "Trunk Width (mm)": t["current_girth"],
            "Training Age (years)": round(t["training_age"], 1),
            "True Age (years)": round(t["true_age"], 1),
            "Status": "Archived" if t["is_archived"] else "Active"
        } for t in trees_data])
        trees_df.to_excel(writer, sheet_name="Trees Overview", index=False)
        
        # Work history
        updates_data = []
        for tree in trees_data:
            for update in tree["updates"]:
                updates_data.append({
                    "Tree Number": tree["tree_number"],
                    "Tree Name": tree["tree_name"],
                    "Date": update["date"],
                    "Trunk Width (mm)": update["girth"],
                    "Work Performed": update["work_performed"]
                })
        pd.DataFrame(updates_data).to_excel(writer, sheet_name="Work History", index=False)
        
        # Reminders
        reminders_data = []
        for tree in trees_data:
            for reminder in tree["reminders"]:
                reminders_data.append({
                    "Tree Number": tree["tree_number"],
                    "Tree Name": tree["tree_name"],
                    "Date": reminder["date"],
                    "Message": reminder["message"],
                    "Status": "Completed" if reminder["is_completed"] else "Pending"
                })
        pd.DataFrame(reminders_data).to_excel(writer, sheet_name="Reminders", index=False)
    
    # Create zip file
    zip_path = f"{export_path}.zip"
    with ZipFile(zip_path, 'w') as zipf:
        for root, dirs, files in os.walk(export_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, export_path)
                zipf.write(file_path, arcname)
    
    # Clean up temporary export directory
    shutil.rmtree(export_path)
    
    return zip_path


def import_bonsai_data(db: Session, zip_file_path: str, image_dir="bonsai_images"):
    """
    Import bonsai data and images from a structured ZIP archive.

    Parameters:
    db (Session): Database session
    zip_file_path (str): Path to the ZIP file containing the backup
    image_dir (str): Directory where bonsai images will be stored

    Returns:
    bool: True if successful, False otherwise
    """
    try:
        # Extract ZIP file
        with tempfile.TemporaryDirectory() as temp_dir:
            with ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Load tree data from JSON
            json_file_path = os.path.join(temp_dir, "trees_data.json")
            if not os.path.exists(json_file_path):
                raise FileNotFoundError("Missing trees_data.json in backup")

            with open(json_file_path, 'r', encoding='utf-8') as f:
                trees_data = json.load(f)

            # Clear existing data
            db.query(Photo).delete()
            db.query(TreeUpdate).delete()
            db.query(Reminder).delete()
            db.query(Tree).delete()
            db.commit()

            # Restore trees and related data
            for tree_data in trees_data:
                species = db.query(Species).filter_by(name=tree_data["species"]).first()
                if not species:
                    species = Species(name=tree_data["species"])
                    db.add(species)
                    db.commit()

                tree = Tree(
                    tree_number=tree_data["tree_number"],
                    tree_name=tree_data["tree_name"],
                    species_id=species.id,
                    date_acquired=datetime.fromisoformat(tree_data["date_acquired"]),
                    origin_date=datetime.fromisoformat(tree_data["origin_date"]),
                    current_girth=tree_data["current_girth"],
                    notes=tree_data["notes"],
                    is_archived=tree_data["is_archived"]
                )
                db.add(tree)
                db.commit()

                # Restore updates
                for update in tree_data["updates"]:
                    db.add(TreeUpdate(
                        tree_id=tree.id,
                        update_date=datetime.fromisoformat(update["date"]),
                        girth=update["girth"],
                        work_performed=update["work_performed"]
                    ))

                # Restore reminders
                for reminder in tree_data["reminders"]:
                    db.add(Reminder(
                        tree_id=tree.id,
                        reminder_date=datetime.fromisoformat(reminder["date"]),
                        message=reminder["message"],
                        is_completed=reminder["is_completed"]
                    ))

                db.commit()

            # Restore images and photo records
            extracted_images_path = os.path.join(temp_dir, "images")
            if os.path.exists(extracted_images_path):
                for tree_folder in os.listdir(extracted_images_path):
                    tree_images_path = os.path.join(extracted_images_path, tree_folder)
                    destination_path = os.path.join(image_dir, tree_folder)
                    os.makedirs(destination_path, exist_ok=True)

                    # Find the tree in the database
                    tree = db.query(Tree).filter_by(tree_number=tree_folder).first()
                    if not tree:
                        continue  # Skip if tree is missing

                    for image_file in os.listdir(tree_images_path):
                        src_file_path = os.path.join(tree_images_path, image_file)
                        dest_file_path = os.path.join(destination_path, image_file)

                        # Copy the image
                        shutil.copy2(src_file_path, dest_file_path)

                        # Add photo record in the database
                        db.add(Photo(
                            tree_id=tree.id,
                            file_path=dest_file_path,
                            photo_date=datetime.strptime(image_file[:8], "%Y%m%d"),  # Extract date from filename
                            description="Imported photo",
                            is_starred=0
                        ))

                db.commit()

            return True
    except Exception as e:
        print(f"Error importing data: {e}")
        return False


def get_exif_date(image_path):
    """Extract date from image EXIF data if available"""
    try:
        image = Image.open(image_path)
        exif = {
            PIL.ExifTags.TAGS[k]: v
            for k, v in image._getexif().items()
            if k in PIL.ExifTags.TAGS
        }
        date_str = exif.get('DateTimeOriginal')
        if date_str:
            return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except:
        pass
    return datetime.now()

def generate_tree_number(db):
    """Generate a unique tree number"""
    tree_count = db.query(Tree).count()
    return f"BON-{tree_count + 1:03d}"

def get_existing_species(db):
    """Get list of existing species from database"""
    return [species.name for species in db.query(Species).order_by(Species.name).all()]

def get_or_create_species(db, species_name):
    """Get existing species or create new one"""
    species = db.query(Species).filter(Species.name == species_name).first()
    if not species:
        species = Species(name=species_name)
        db.add(species)
        db.commit()
    return species

def save_uploaded_images(uploaded_files):
    """Save multiple uploaded images and return their paths"""
    image_paths = []
    for uploaded_file in uploaded_files:
        path = save_uploaded_image(uploaded_file)
        image_paths.append(path)
    return image_paths

def show_work_history(tree_id):
    """Display work history, trunk measurements, and reminders for a specific tree"""
    db = SessionLocal()
    try:
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        # Back button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        st.header(f"Work History: {tree.tree_name} *({tree.tree_number})*")
        
        # Growth History Chart in Expander
        with st.expander("📈 Growth History"):
            # Get all girth measurements from updates
            measurements = db.query(TreeUpdate).filter(
                TreeUpdate.tree_id == tree_id,
                TreeUpdate.girth.isnot(None)
            ).order_by(TreeUpdate.update_date).all()
            
            if measurements:
                # Prepare data for chart
                data = [{
                    'date': update.update_date.strftime('%Y-%m'),
                    'trunk width': update.girth
                } for update in measurements]
                
                # Create chart using Streamlit
                df = pd.DataFrame(data)
                df = df.groupby('date').first().reset_index()
                fig = px.line(df, x='date', y='trunk width', 
                    markers=True,
                    line_shape="spline",  # Smooth line
                    color_discrete_sequence=['#2E8B57'])  # Forest green)
                fig.update_layout(
                xaxis_title="Date",
                yaxis_title="Trunk width (mm)",  # Adjust units as needed
                yaxis=dict(rangemode='tozero', gridcolor="lightgrey"),
                xaxis=dict(tickangle=-45, showgrid=False, tickformat="%b %Y"),
                plot_bgcolor='rgba(0,0,0,0)',
                hovermode="x unified"
            )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No growth measurements recorded yet.")
        
        # Pending Reminders in Expander
        with st.expander("⏰ Pending Reminders"):
            pending_reminders = db.query(Reminder).filter(
                Reminder.tree_id == tree_id,
                Reminder.is_completed == 0,
                Reminder.reminder_date >= datetime.now()
            ).order_by(Reminder.reminder_date).all()
            
            if pending_reminders:
                for reminder in pending_reminders:
                    with st.container():
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            st.write(reminder.reminder_date.strftime('%Y-%m-%d'))
                        with col2:
                            st.write(reminder.message)
                        st.markdown("---")
            else:
                st.info("No pending reminders.")
        
        # Initialize session state for edit mode if it doesn't exist
        if 'edit_update_id' not in st.session_state:
            st.session_state.edit_update_id = None
        
        # Get tree updates
        updates = db.query(TreeUpdate).filter(
            TreeUpdate.tree_id == tree_id
        ).order_by(TreeUpdate.update_date.desc()).all()
        
        # Display edit form if in edit mode
        if st.session_state.edit_update_id is not None:
            update_to_edit = db.query(TreeUpdate).get(st.session_state.edit_update_id)
            if update_to_edit:
                st.subheader("Edit Update")
                
                # Create form for editing
                with st.form(key="edit_update_form"):
                    edit_date = st.date_input("Date", value=update_to_edit.update_date)
                    edit_girth = st.number_input("Trunk Width (mm)", 
                                            value=float(update_to_edit.girth) if update_to_edit.girth else 0.0,
                                            min_value=0.0, 
                                            format="%.1f",
                                            step=0.1)
                    edit_work = st.text_area("Work Performed", value=update_to_edit.work_performed)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        save_button = st.form_submit_button("Save Changes")
                    with col2:
                        cancel_button = st.form_submit_button("Cancel")
                
                # Handle form submission
                if save_button:
                    # Update the database
                    update_to_edit.update_date = datetime.combine(edit_date, datetime.min.time())
                    update_to_edit.girth = edit_girth
                    update_to_edit.work_performed = edit_work
                    db.commit()
                    
                    # Exit edit mode
                    st.session_state.edit_update_id = None
                    st.success("Update saved successfully!")
                    st.rerun()
                
                if cancel_button:
                    # Exit edit mode without saving
                    st.session_state.edit_update_id = None
                    st.rerun()
        
        # Display work history
        if updates:
            for update in updates:
                with st.container():
                    # Use columns for layout
                    col1, col2, col3 = st.columns([14, 1, 1])
                    
                    with col1:
                        # Date and work description
                        st.markdown(f"**{update.update_date.strftime('%Y-%m-%d')}**")
                        if update.girth:
                            st.markdown(f"*Trunk width: {update.girth} mm*")
                        st.write(update.work_performed)
                    
                    with col2:
                        # Edit button
                        if st.button("✏️", key=f"edit_{update.id}", use_container_width=True):
                            st.session_state.edit_update_id = update.id
                            st.rerun()
                    
                    with col3:
                        # Delete button with confirmation
                        if st.button("🗑️", key=f"delete_{update.id}", use_container_width=True):
                            st.session_state[f"confirm_delete_{update.id}"] = True
                            st.rerun()
                    
                    # Show confirmation dialog if delete was clicked
                    if st.session_state.get(f"confirm_delete_{update.id}", False):
                        st.warning(f"Are you sure you want to delete this entry from {update.update_date.strftime('%Y-%m-%d')}?")
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Yes, Delete", key=f"confirm_yes_{update.id}"):
                                # Delete the update
                                db.delete(update)
                                db.commit()
                                st.session_state.pop(f"confirm_delete_{update.id}")
                                st.success("Entry deleted!")
                                st.rerun()
                        with col2:
                            if st.button("Cancel", key=f"confirm_no_{update.id}"):
                                st.session_state.pop(f"confirm_delete_{update.id}")
                                st.rerun()
                    
                    # Add separator between updates
                    st.markdown("---")
        else:
            st.info("No work history recorded yet.")
            
    finally:
        db.close()

def create_responsive_grid(trees, db):
    """Creates a responsive grid layout that adjusts based on container width"""
    # We'll use container width classes from streamlit
    container_width = st.get_container_width() if hasattr(st, 'get_container_width') else None
    
    # Default to 1 column for mobile-first approach
    num_cols = 1
    
    # Create columns based on available width
    for i in range(0, len(trees), num_cols):
        # Create a row using columns
        cols = st.columns(num_cols)
        
        # Fill each column in the row
        for j in range(num_cols):
            idx = i + j
            if idx < len(trees):
                with cols[j]:
                    create_tree_card(trees[idx], db)

def create_tree_card(tree, db):
    """Update create_tree_card function with more responsive layout"""
    with st.container():
        with st.expander(f"**{tree.tree_name.strip()}**  \n*{tree.species_info.name.strip()}*", expanded=False):
            # Make buttons more touch-friendly on mobile
            button_cols = st.columns([2, 1, 2])
            
            with button_cols[0]:
                if st.button("Gallery", key=f"gallery_{tree.id}", use_container_width=True):
                    st.session_state.page = "Tree Gallery"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            

            
            with button_cols[2]:
                if st.button("History", key=f"work_history_{tree.id}", use_container_width=True):
                    st.session_state.page = "Work History"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            # Image handling
            display_photo = (
                db.query(Photo)
                .filter(Photo.tree_id == tree.id, Photo.is_starred == 1)
                .first()
                or
                db.query(Photo)
                .filter(Photo.tree_id == tree.id)
                .order_by(Photo.photo_date.desc())
                .first()
            )
            
            if display_photo and os.path.exists(display_photo.file_path):
                st.image(display_photo.file_path, use_container_width =True)
            else:
                st.image("https://via.placeholder.com/150", use_container_width =True)
            
            # Rest of the card content...
            if tree.notes:
                st.write("**Note:**", tree.notes)
            
            latest_update = db.query(TreeUpdate).filter(
                TreeUpdate.tree_id == tree.id
            ).order_by(TreeUpdate.update_date.desc()).first()
            
            if latest_update:
                st.write(f"**Last Update:** {latest_update.update_date.strftime('%Y-%m-%d')}")
            
            # Action buttons in a single row
            col1, col2, col3 = st.columns([2, 1, 2])
            with col1:
                if st.button(f"Edit", key=f"edit_{tree.id}", use_container_width=True):
                    st.session_state.page = "Edit Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            with col3:
                if st.button("Add Update", key=f"update_{tree.id}", use_container_width=True):
                    st.session_state.page = "Update Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
                

def set_page_and_tree(page, tree_id=None):
    """Helper function to set both page and selected tree"""
    st.session_state.page = page
    st.session_state.selected_tree = tree_id
    
def handle_edit_cancel(photo_id):
    """Handle canceling edit mode"""
    st.session_state[f"edit_mode_{photo_id}"] = False

def handle_delete_cancel(photo_id):
    """Handle canceling delete confirmation"""
    st.session_state[f"confirm_delete_{photo_id}"] = False

def show_tree_gallery(tree_id):
    """Display gallery view for a specific tree with photo management functionality"""
    db = SessionLocal()
    try:
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        # Reset states only when first entering the gallery
        if 'gallery_initialized' not in st.session_state:
            for key in list(st.session_state.keys()):
                if key.startswith(('confirm_delete_', 'edit_mode_')):
                    del st.session_state[key]
            st.session_state.gallery_initialized = True
        
        # Add "Back to Collection" button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.session_state.gallery_initialized = False
            st.rerun()
        
        
        
        st.header(f"{tree.species_info.name} *({tree.tree_number})*")
            
        photos = db.query(Photo).filter(
            Photo.tree_id == tree_id
        ).order_by(Photo.photo_date).all()
        
        # No photos message
        if not photos:
            st.info("No photos available for this tree.")
            return
        
        col1, col2, col3 = st.columns([1, 8, 6])
        
        with col2:
            # Photo display loop
            for photo in photos:
                tree_galler_grid = grid(1,[10,1.5,1.5,1.5])
                if os.path.exists(photo.file_path):
                    # Create a unique key for each photo's container

                    tree_galler_grid.image(photo.file_path, use_container_width =True)
                            
                    # Initialize session state for edit mode
                    edit_key = f"edit_mode_{photo.id}"
                    if edit_key not in st.session_state:
                        st.session_state[edit_key] = False
                    
                    if st.session_state[edit_key]:
                        # Show date input when in edit mode
                        new_date = tree_galler_grid.date_input(
                            "Edit Photo Date",
                            value=photo.photo_date.date(),
                            key=f"date_input_{photo.id}",
                            label_visibility="collapsed"
                        )
                        col1, col2, col3 = st.columns([1,1,8])
                        # Save button
                        with col1:
                            if st.button("Save", key=f"save_{photo.id}", use_container_width=True):
                                photo.photo_date = datetime.combine(new_date, datetime.min.time())
                                db.commit()
                                st.session_state[edit_key] = False
                                st.rerun()
                        
                        with col2:
                        # Cancel button
                            if st.button("Cancel", key=f"cancel_{photo.id}", use_container_width=True):
                                st.session_state[edit_key] = False
                                st.rerun()
                    
                    
                    else:
                        # Display current date when not in edit mode
                        tree_galler_grid.write(f"Date: {photo.photo_date.strftime('%Y-%m-%d')}")
                        with tree_galler_grid.container():
                            # Display the image
                            # Star/unstar button
                            star_icon = "⭐" if photo.is_starred else "☆"
                            if st.button(star_icon, key=f"star_{photo.id}", use_container_width=True, type = "secondary"):
                                # Unstar all other photos for this tree
                                if not photo.is_starred:
                                    db.query(Photo).filter(
                                        Photo.tree_id == tree_id,
                                        Photo.id != photo.id
                                    ).update({"is_starred": 0})
                                # Toggle star status for this photo
                                photo.is_starred = 1 - photo.is_starred
                                db.commit()
                                st.rerun()
                        
                    

                    if tree_galler_grid.button("Edit Date", key=f"edit_button_{photo.id}",use_container_width=True):
                        st.session_state[f"edit_mode_{photo.id}"] = True
                        st.rerun()
                    

                    # Delete button and confirmation handling
                    delete_key = f"confirm_delete_{photo.id}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False
                    
                    if not st.session_state[delete_key]:
                        if tree_galler_grid.button("Delete", key=f"delete_{photo.id}",use_container_width=True):
                            st.session_state[delete_key] = True
                            st.rerun()
                    else:
                        st.warning("Are you sure you want to delete this photo?")
                        # Yes button
                        if st.button("Yes", key=f"confirm_yes_{photo.id}"):
                            if os.path.exists(photo.file_path):
                                os.remove(photo.file_path)
                            db.delete(photo)
                            db.commit()
                            st.session_state[delete_key] = False
                            st.rerun()
                        
                        # No button
                        if st.button("No", key=f"confirm_no_{photo.id}"):
                            st.session_state[delete_key] = False
                            st.rerun()
                            
                st.markdown("")

    finally:
        db.close()
        
def show_update_form(tree_id):
    """Display the update form for a specific tree"""
    db = SessionLocal()
    try:
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        st.header(f"Update: {tree.tree_name} ({tree.tree_number})")

        # Initialize session state for this specific tree's reminder
        session_key = f"set_reminder_{tree_id}"
        if session_key not in st.session_state:
            st.session_state[session_key] = False

        # Checkbox outside the form for immediate feedback
        set_reminder = st.checkbox(
            "Set Reminder",
            value=st.session_state[session_key],
            key=f"reminder_check_{tree_id}",
            on_change=lambda: st.session_state.update({session_key: not st.session_state[session_key]})
        )

        with st.form(f"tree_update_form_{tree_id}"):
            # Create columns for date and girth inputs
            col1, col2 = st.columns(2)
            
            with col1:
                current_girth = st.number_input(
                    "New Trunk Width (mm)", 
                    value=tree.current_girth if tree.current_girth else 0.0,
                    step=0.1
                )
            
            with col2:
                update_date = st.date_input(
                    "Update Date",
                    value=datetime.now().date(),
                    help="Date when this work was performed"
                )
            
            work_description = st.text_area("Work Performed")
            
            uploaded_files = st.file_uploader(
                "Add Photos", 
                type=['png', 'jpg', 'jpeg'],
                accept_multiple_files=True
            )
            
            # Show reminder fields based on checkbox state
            if st.session_state[session_key]:
                reminder_date = st.date_input("Reminder Date (required)")
                reminder_message = st.text_input("Reminder Message (required)")
            else:
                reminder_date = None
                reminder_message = None
            
            col1, col2, col3 = st.columns([1,1,1])
            
            with col1:
                if st.form_submit_button("Save Update"):
                    # Validate reminder fields if checkbox is checked
                    if st.session_state[session_key] and (not reminder_date or not reminder_message):
                        st.error("Please fill in both reminder fields when setting a reminder")
                        st.rerun()
                    
                    # Create tree update with specified date
                    update = TreeUpdate(
                        tree_id=tree_id,
                        update_date=datetime.combine(update_date, datetime.min.time()),
                        girth=current_girth,
                        work_performed=work_description
                    )
                    db.add(update)
                    
                    # Update tree's current girth
                    tree.current_girth = current_girth
                    
                    # Save photos
                    if uploaded_files:
                        image_paths = save_uploaded_images(uploaded_files)
                        for path in image_paths:
                            photo_date = get_exif_date(path)
                            photo = Photo(
                                tree_id=tree_id,
                                file_path=path,
                                photo_date=photo_date,
                                description=work_description
                            )
                            db.add(photo)
                    
                    # Create reminder if specified
                    if st.session_state[session_key]:
                        reminder = Reminder(
                            tree_id=tree_id,
                            reminder_date=datetime.combine(reminder_date, datetime.min.time()),
                            message=reminder_message
                        )
                        db.add(reminder)
                    
                    db.commit()
                    st.success("Update saved successfully!")
                    # Reset the reminder state after successful submission
                    st.session_state[session_key] = False
                    st.session_state.page = "View Trees"
                    st.rerun()
            with col3:
                if st.form_submit_button("Add to Graveyard"):
                    update = TreeUpdate(
                        tree_id=tree_id,
                        update_date=datetime.now(),
                        work_performed=work_description
                    )
                    db.add(update)
                    tree.is_archived = 1
                    db.commit()
                    st.success(f"Tree {tree.tree_number} added to the graveyard.")
                    st.session_state.page = "Graveyard"
                    st.rerun()
    finally:
        db.close()

def show_add_tree_form():
    """Display the form for adding a new tree"""
    # Get existing species list
    db = SessionLocal()
    existing_species = get_existing_species(db)
    
    # Ensure "Add New Species" is an option
    species_options = ["Add New Species"] + existing_species
    
    # Determine current species selection (default to last species or "Add New Species")
    current_species = existing_species[-1] if existing_species else "Add New Species"
    
    # Create a container with a border
    with st.container(border=True):
        tree_name = st.text_input(
            "Tree Name",
            help="Give your tree a personal name"
        )
        
        # Species selection
        species_selection = st.selectbox(
            "Species*",
            options=species_options,
            index=species_options.index(current_species),
            help="Select existing species or add new one"
        )
        
        # Conditionally show new species input
        if species_selection == "Add New Species":
            new_species = st.text_input(
                "Enter New Species Name*",
                help="Enter the botanical or common name of your tree"
            )
        
        with st.form(key="new_tree_form", clear_on_submit=True, border=False):
            # Get a new tree number (display only)
            new_tree_number = generate_tree_number(db)
            st.info(f"Tree Number will be: {new_tree_number}")
            
            # Rest of the form
            col1, col2 = st.columns(2)
            
            with col1:
                current_girth = st.number_input("Current Trunk Width (mm)", 
                    min_value=0.0, step=0.1)
            
            with col2:
                date_acquired = st.date_input("Date Acquired*",
                    help="When did you acquire this tree?")
                origin_date = st.date_input("Origin Date*",
                    help="Estimated start date of the tree (for age calculation)")
                
            notes = st.text_area("Notes", 
                help="Any special notes about this tree")
            
            uploaded_file = st.file_uploader("Upload Initial Photo", 
                type=['png', 'jpg', 'jpeg'])
            
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
                st.image(image, caption="Preview", width=300)
            
            submit_button = st.form_submit_button("Add Tree")
            
            if submit_button:
                if not species_selection:
                    st.error("Species is required!")
                    return
                
                try:
                    # Determine species (new or existing)
                    if species_selection == "Add New Species":
                        species = new_species
                    else:
                        species = species_selection
                    
                    # Get or create species
                    species_obj = get_or_create_species(db, species)
                    
                    # Create new tree
                    new_tree = Tree(
                        tree_number=new_tree_number,
                        tree_name=tree_name,
                        species_id=species_obj.id,
                        date_acquired=datetime.combine(date_acquired, datetime.min.time()),
                        origin_date=datetime.combine(origin_date, datetime.min.time()),
                        current_girth=current_girth,
                        notes=notes
                    )
                    
                    db.add(new_tree)
                    db.commit()
                    
                    # Handle photo if uploaded
                    if uploaded_file:
                        image_path = save_uploaded_image(uploaded_file)
                        photo = Photo(
                            tree_id=new_tree.id,
                            file_path=image_path,
                            photo_date=datetime.now(),
                            description="Initial photo"
                        )
                        db.add(photo)
                        db.commit()
                    
                    st.success(f"Tree {new_tree.tree_number} added successfully!")
                    st.session_state.page = "View Trees"
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error adding tree: {str(e)}")
        
    db.close()

def show_graveyard_trees():
    """Display trees in the graveyard with their final update."""
    st.header("Bonsai Graveyard")
    
    db = SessionLocal()
    try:
        graveyard_trees = db.query(Tree).filter(Tree.is_archived == 1).all()
        
        if not graveyard_trees:
            st.info("No trees in the graveyard yet.")
            return
        
        for tree in graveyard_trees:
            with st.container():
                col1, col2, col3 = st.columns([10, 1, 1])
                
                with col1:
                    st.write(f"**{tree.tree_name.strip()}** ({tree.tree_number})  \n*{tree.species_info.name.strip()}*")
                    
                    last_update = (
                        db.query(TreeUpdate)
                        .filter(TreeUpdate.tree_id == tree.id)
                        .order_by(TreeUpdate.update_date.desc())
                        .first()
                    )
                    if last_update:
                        st.write(f"**Final Update:** {last_update.work_performed}")
                    else:
                        st.write("No final update recorded.")
                
                with col2:
                    if st.button("Restore", key=f"restore_{tree.id}", use_container_width=True):
                        tree.is_archived = 0
                        db.commit()
                        st.success(f"Tree {tree.tree_number} restored!")
                        st.rerun()
                
                with col3:
                    if state_button("Delete Forever", key=f"delete_{tree.id}", use_container_width=True):
                        if "confirm_delete" not in st.session_state:
                            st.session_state.confirm_delete = False
                        
                        if not st.session_state.confirm_delete:
                            st.warning("Are you sure you want to delete this tree forever?")
                            if st.button("Yes, Delete", key=f"confirm_delete_{tree.id}"):
                                st.session_state.confirm_delete = True
                                st.rerun()
                        else:
                            # Delete associated photos from filesystem
                            for photo in tree.photos:
                                if os.path.exists(photo.file_path):
                                    os.remove(photo.file_path)
                            
                            # Delete tree from database
                            db.delete(tree)
                            db.commit()
                            st.success(f"Tree {tree.tree_number} deleted permanently!")
                            st.rerun()
                        
            st.markdown("---")
    finally:
        db.close()

def show_edit_tree_form(tree_id):
    """Display the form for editing an existing tree's details"""
    db = SessionLocal()
    try:
        # Fetch the existing tree
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        # Get existing species list
        existing_species = get_existing_species(db)
        
        # Ensure "Add New Species" is an option
        species_options = ["Add New Species"] + existing_species
        
        # Determine current species selection
        current_species = tree.species_info.name if tree.species_info else "Add New Species"
        
        with st.container(border=True):
            
            st.header(f"Edit Tree: {tree.tree_number}")
            
            tree_name = st.text_input(
                "Tree Name", 
                value=tree.tree_name,
                help="Give your tree a personal name"
            )
            
            # Species selection
            species_selection = st.selectbox(
                "Species*",
                options=species_options,
                index=species_options.index(current_species),
                help="Select existing species or add new one"
            )
            
            # Conditionally show new species input
            if species_selection == "Add New Species":
                new_species = st.text_input(
                    "Enter New Species Name*",
                    help="Enter the botanical or common name of your tree"
                )
            
            with st.form(key=f"edit_tree_form_{tree_id}", clear_on_submit=True, border=False):

                
                
                # Dates
                col1, col2 = st.columns(2)
                with col1:
                    date_acquired = st.date_input(
                        "Date Acquired*",
                        value=tree.date_acquired,
                        help="When did you acquire this tree?"
                    )
                
                with col2:
                    origin_date = st.date_input(
                        "Origin Date*", 
                        value=tree.origin_date,
                        help="Estimated start date of the tree (for age calculation)"
                    )
                
                # Notes
                notes = st.text_area(
                    "Notes", 
                    value=tree.notes or "",
                    help="Any special notes about this tree"
                )
                
                # Submit button
                submit_button = st.form_submit_button("Save Changes")
                
                if submit_button:
                    try:
                        # Determine species (new or existing)
                        if species_selection == "Add New Species":
                            species = new_species
                        else:
                            species = species_selection
                        
                        # Get or create species
                        species_obj = get_or_create_species(db, species)
                        
                        # Update tree details
                        tree.tree_name = tree_name
                        tree.species_id = species_obj.id
                        tree.date_acquired = datetime.combine(date_acquired, datetime.min.time())
                        tree.origin_date = datetime.combine(origin_date, datetime.min.time())
                        tree.notes = notes
                        
                        db.commit()
                        
                        st.success("Tree details updated successfully!")
                        st.session_state.page = "View Trees"
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error updating tree: {str(e)}")
    
    finally:
        db.close()

def get_pending_reminders(db):
    """Get reminders that are due or overdue and not yet completed"""
    today = datetime.now().date()
    pending_reminders = db.query(Reminder, Tree).join(Tree).filter(
        Reminder.reminder_date <= today,
        Reminder.is_completed == 0
    ).all()
    return pending_reminders

def show_reminder_popup():
    """Check for and display pending reminders when app starts"""
    # Only run this once at startup
    if 'reminders_checked' not in st.session_state:
        st.session_state.reminders_checked = False
        
        db = SessionLocal()
        try:
            pending_reminders = get_pending_reminders(db)
            
            if pending_reminders:
                # Initialize checkbox states
                for reminder, _ in pending_reminders:
                    if f"reminder_{reminder.id}" not in st.session_state:
                        st.session_state[f"reminder_{reminder.id}"] = False
                
                # Create a dialog using a container with custom styling
                with st.container(key="reminder_popup",border=True):
                    st.subheader("📅 Pending Reminders")
                    
                    st.markdown("""
                                <style>
                                    .stCheckbox label {
                                        white-space: pre-line;
                                    }
                                </style>
                            """, unsafe_allow_html=True)
                    
                    # Add a form to handle the checkboxes
                    with st.form(key="reminder_form",border=False):
                        for reminder, tree in pending_reminders:
                            reminder_key = f"reminder_{reminder.id}"
                            # Add CSS to allow line breaks in checkbox labels
                            

                            # Create the checkbox with a newline separating the two lines
                            st.checkbox(
                                f"**Due: {reminder.reminder_date.strftime('%Y-%m-%d')}** (*{tree.tree_name}*)\n{reminder.message}",
                                key=reminder_key
                            )
                        
                        # Submit button to process checked reminders
                        if st.form_submit_button("Mark Selected as Complete"):
                            for reminder, _ in pending_reminders:
                                if st.session_state[f"reminder_{reminder.id}"]:
                                    reminder.is_completed = 1
                                    db.commit()
                            st.session_state.reminders_checked = True
                            st.rerun()
                    
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.session_state.reminders_checked = True
                
        finally:
            db.close()

def get_exif_orientation(image_path):
    """Get the EXIF orientation tag from an image"""
    try:
        image = Image.open(image_path)
        if hasattr(image, '_getexif'):  # Check if image has EXIF data
            exif = image._getexif()
            if exif:
                # Find the orientation tag (274 is the standard tag for orientation)
                for tag_id in PIL.ExifTags.TAGS:
                    if PIL.ExifTags.TAGS[tag_id] == 'Orientation':
                        orientation = exif.get(tag_id)
                        return orientation
    except:
        pass
    return 1  # Default orientation if no EXIF data found

def fix_image_orientation(image_path):
    """Fix image orientation based on EXIF data and save the corrected image"""
    try:
        image = Image.open(image_path)
        if hasattr(image, '_getexif'):  # Check if image has EXIF data
            orientation = get_exif_orientation(image_path)
            
            # Rotate or flip based on EXIF orientation tag
            if orientation == 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                image = image.transpose(Image.ROTATE_180)
            elif orientation == 4:
                image = image.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                image = image.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_90)
            elif orientation == 6:
                image = image.transpose(Image.ROTATE_270)
            elif orientation == 7:
                image = image.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270)
            elif orientation == 8:
                image = image.transpose(Image.ROTATE_90)
            
            # Save the corrected image
            image.save(image_path, quality=95, exif=image.info.get('exif'))
            
    except Exception as e:
        print(f"Error fixing image orientation: {str(e)}")

def save_uploaded_image(uploaded_file):
    """Save uploaded image to the images directory with orientation correction"""
    image_dir = os.path.join('data', 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_extension = os.path.splitext(uploaded_file.name)[1]
    filename = f"tree_{timestamp}{file_extension}"
    
    file_path = os.path.join(image_dir, filename)
    
    # Save the original uploaded file
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Fix the orientation
    fix_image_orientation(file_path)
    
    return file_path

def save_uploaded_logo(uploaded_file):
    """Save uploaded logo to the images directory with orientation correction"""
    logo_dir = os.path.join('data', 'system')
    os.makedirs(logo_dir, exist_ok=True)
    
    file_extension = os.path.splitext(uploaded_file.name)[1]
    filename = f"logo{file_extension}"
    file_path = os.path.join(logo_dir, filename)
    
    # Save the original uploaded file
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Fix the orientation
    fix_image_orientation(file_path)
    
    return file_path

def get_or_create_settings(db):
    """Get existing settings or create default ones"""
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(
            app_title="Bonsai Tracker",
            sidebar_image="C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png"
        )
        db.add(settings)
        db.commit()
    return settings

def show_settings_form():
    """Display and handle the settings form"""
    
    col1, col2, col3 = st.columns([1, 10, 5])
        
    with col2:
        st.header("Customize Profile")
        
        db = SessionLocal()
        try:
            settings = get_or_create_settings(db)
            
            
            with st.form("settings_form"):
                # App title input
                new_title = st.text_input(
                    "Profile Name",
                    value=settings.app_title,
                    help="Customize the profile title shown in the sidebar"
                )
                
                # Logo upload
                new_logo = st.file_uploader(
                    "Upload New Profile Image",
                    type=['png', 'jpg', 'jpeg'],
                    help="Upload a new logo image (recommended size: 125x125 pixels)"
                )
                
                if new_logo:
                    st.image(new_logo, width=125)
                
                col1, col2, col3 = st.columns([2,4,2])
                
                with col1:
                    if st.form_submit_button("Save Settings", use_container_width=True):
                        try:
                            settings.app_title = new_title
                            
                            if new_logo:
                                logo_path = save_uploaded_logo(new_logo)
                                settings.sidebar_image = logo_path
                            
                            db.commit()
                            st.success("Settings updated successfully!")
                            st.session_state.page = "View Trees"
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Error saving settings: {str(e)}")
                        
                
                                    # Function to confirm action
            with st.expander("⚠️ Import Backup"):
                st.warning("This action will **overwrite** all existing bonsai data. Make sure you have a recent backup before proceeding!")

                # Initialize session state if needed
                if 'restore_state' not in st.session_state:
                    st.session_state.restore_state = "upload"
                
                # File uploader (shown in initial state)
                if st.session_state.restore_state == "upload":
                    uploaded_file = st.file_uploader(
                        "Upload Backup File",
                        type=['zip'],
                        help="Select a backup file created by the export function"
                    )

                    # Checkbox to enable the button
                    confirm_checkbox = st.checkbox("I understand this will erase existing data and replace it with the backup.")

                    # Restore button (enabled only if checkbox is checked)
                    if st.button("⚠️ Restore from Backup", type="primary", disabled=not confirm_checkbox):
                        if uploaded_file is not None:
                            # Save file to temporary location
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                st.session_state.temp_path = tmp_file.name
                            # Move to confirmation state
                            st.session_state.restore_state = "confirm"
                            st.rerun()
                        else:
                            st.error("Please upload a backup file first.")
                
                # Final confirmation state
                elif st.session_state.restore_state == "confirm":
                    st.error("⚠️ **Final Confirmation Required!** This will erase all existing data.")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Yes, Restore Data", type="primary"):
                            with st.spinner("Restoring from backup..."):
                                success = import_bonsai_data(db, st.session_state.temp_path)
                                if success:
                                    st.success("Backup restored successfully!")
                                    # Clean up
                                    st.session_state.restore_state = "upload"
                                    if hasattr(st.session_state, 'temp_path'):
                                        del st.session_state.temp_path
                                else:
                                    st.error("Failed to restore backup.")
                    
                    with col2:
                        if st.button("❌ Cancel"):
                            st.session_state.restore_state = "upload"
                            if hasattr(st.session_state, 'temp_path'):
                                # Clean up temp file
                                try:
                                    os.remove(st.session_state.temp_path)
                                except:
                                    pass
                                del st.session_state.temp_path
                            st.rerun()


        finally:
            db.close()

def show_species_notes():
    """
    Display the species notes page with options to manage species.
    """
    st.header("Species Notes")
    
    # Add back button
    if st.button("← Back to Collection"):
        st.session_state.page = "View Trees"
        st.rerun()
    
    # Add new species button
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("➕ Add New Species", use_container_width=True):
            st.session_state.show_add_species = True
    
    # Add new species form
    if st.session_state.get("show_add_species", False):
        with st.form("add_species_form"):
            st.subheader("Add New Species")
            species_name = st.text_input("Species Name", key="new_species_name")
            species_notes = st.text_area("Species Notes (Markdown supported)", 
                                        height=300,
                                        help="You can use markdown formatting for your notes.")
            
            col1, col2 = st.columns(2)
            with col1:
                submit = st.form_submit_button("Save Species")
            with col2:
                cancel = st.form_submit_button("Cancel")
            
            if submit and species_name:
                db = SessionLocal()
                try:
                    # Check if species already exists
                    existing = db.query(Species).filter(Species.name == species_name).first()
                    if existing:
                        st.error(f"Species '{species_name}' already exists.")
                    else:
                        new_species = Species(name=species_name, notes=species_notes)
                        db.add(new_species)
                        db.commit()
                        st.success(f"Species '{species_name}' added successfully!")
                        st.session_state.show_add_species = False
                        st.rerun()
                except Exception as e:
                    st.error(f"Error adding species: {str(e)}")
                finally:
                    db.close()
            
            if cancel:
                st.session_state.show_add_species = False
                st.rerun()
    
    # Display species list
    db = SessionLocal()
    try:
        species_list = db.query(Species).order_by(Species.name).all()
        
        if not species_list:
            st.info("No species have been added yet. Click 'Add New Species' to get started.")
        else:
            # Create two columns: one for the list and one for the notes display
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("Species List")
                for species in species_list:
                    col_a, col_b, col_c = st.columns([3, 1, 1])
                    with col_a:
                        if st.button(f"{species.name}", key=f"view_{species.id}", use_container_width=True):
                            st.session_state.selected_species = species.id
                            st.rerun()
                    with col_b:
                        if st.button("✏️", key=f"edit_{species.id}"):
                            st.session_state.selected_species = species.id
                            st.session_state.page = "Edit Species"
                            st.rerun()
                    with col_c:
                        if st.button("🗑️", key=f"delete_{species.id}"):
                            st.session_state.delete_species_id = species.id
                            st.session_state.delete_species_name = species.name
                            st.session_state.show_delete_confirmation = True
                            st.rerun()
            
            # Show species notes if one is selected
            with col2:
                if st.session_state.get("selected_species"):
                    selected = db.query(Species).filter(Species.id == st.session_state.selected_species).first()
                    if selected:
                        st.subheader(f"{selected.name} Notes")
                        
                        # Check if there are trees using this species
                        tree_count = db.query(Tree).filter(Tree.species_id == selected.id).count()
                        if tree_count > 0:
                            st.info(f"This species is used by {tree_count} tree{'s' if tree_count > 1 else ''} in your collection.")
                        
                        # Display formatted notes
                        if selected.notes:
                            st.markdown(selected.notes)
                        else:
                            st.info("No notes available for this species.")
                        
                        # Edit button
                        if st.button("Edit Notes", key="edit_notes"):
                            st.session_state.page = "Edit Species"
                            st.rerun()
                    else:
                        st.info("Select a species from the list to view its notes.")
                else:
                    st.info("Select a species from the list to view its notes.")
        
        # Delete confirmation dialog
        if st.session_state.get("show_delete_confirmation", False):
            with st.container():
                st.warning(f"Are you sure you want to delete '{st.session_state.delete_species_name}'?")
                
                # Check if this species is used by any trees
                tree_count = db.query(Tree).filter(Tree.species_id == st.session_state.delete_species_id).count()
                if tree_count > 0:
                    st.error(f"This species is used by {tree_count} tree{'s' if tree_count > 1 else ''} in your collection. You cannot delete it until you reassign those trees to different species.")
                    if st.button("Cancel", key="cancel_delete"):
                        st.session_state.show_delete_confirmation = False
                        st.rerun()
                else:
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Yes, Delete", key="confirm_delete"):
                            try:
                                species_to_delete = db.query(Species).filter(Species.id == st.session_state.delete_species_id).first()
                                if species_to_delete:
                                    db.delete(species_to_delete)
                                    db.commit()
                                    st.session_state.show_delete_confirmation = False
                                    if st.session_state.get("selected_species") == st.session_state.delete_species_id:
                                        st.session_state.selected_species = None
                                    st.success(f"Species '{st.session_state.delete_species_name}' deleted successfully!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting species: {str(e)}")
                    with col2:
                        if st.button("Cancel", key="cancel_delete"):
                            st.session_state.show_delete_confirmation = False
                            st.rerun()
                            
    except Exception as e:
        st.error(f"Error loading species: {str(e)}")
    finally:
        db.close()

def show_edit_species_form(species_id):
    """Display the form to edit a species"""
    db = SessionLocal()
    try:
        species = db.query(Species).filter(Species.id == species_id).first()
        if not species:
            st.error("Species not found")
            if st.button("Back to Species Notes"):
                st.session_state.page = "Species Notes"
                st.rerun()
            return
        
        st.header(f"Edit {species.name}")
        
        # Back button
        if st.button("← Back to Species Notes"):
            st.session_state.page = "Species Notes"
            st.rerun()
        
        with st.form("edit_species_form"):
            species_name = st.text_input("Species Name", value=species.name)
            
            species_notes = st.text_area("Species Notes (Markdown supported)", 
                                        value=species.notes or "", 
                                        height=400)
            
            col1, col2 = st.columns(2)
            with col1:
                submit = st.form_submit_button("Save Changes")
            with col2:
                cancel = st.form_submit_button("Cancel")
            
            if submit:
                if not species_name:
                    st.error("Species name cannot be empty")
                else:
                    try:
                        # Check if the name already exists (for a different species)
                        existing = db.query(Species).filter(
                            Species.name == species_name, 
                            Species.id != species.id
                        ).first()
                        
                        if existing:
                            st.error(f"Species '{species_name}' already exists.")
                        else:
                            species.name = species_name
                            species.notes = species_notes
                            db.commit()
                            st.success("Species updated successfully!")
                            # Go back to species notes page
                            st.session_state.page = "Species Notes"
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error updating species: {str(e)}")
            
            if cancel:
                st.session_state.page = "Species Notes"
                st.rerun()
        
    except Exception as e:
        st.error(f"Error loading species: {str(e)}")
    finally:
        db.close()

def main():
    st.set_page_config(page_title="Bonsai Tracker", layout="wide", initial_sidebar_state="auto")
    
    with open('C:\\Users\\loudo\\Desktop\\bonsai-tracker\\src\\style.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = "View Trees"
    if 'selected_tree' not in st.session_state:
        st.session_state.selected_tree = None
    if 'selected_species' not in st.session_state:
        st.session_state.selected_species = None
    
    show_reminder_popup()
    
    # Sidebar
    with st.sidebar:
        db = SessionLocal()
        try:
            settings = get_or_create_settings(db)
            
            # Add Settings button to sidebar
            if st.button("⚙️", key="settings"):
                st.session_state.page = "Settings"
                st.rerun()
            
            # Use custom title
            st.header(settings.app_title)
            
            # Use custom logo if it exists and is valid
            if settings.sidebar_image and os.path.exists(settings.sidebar_image):
                st.image(settings.sidebar_image, use_container_width=True)
            else:
                # Fallback to default logo
                st.image("C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png", width=125)
            
            # Create a container to push buttons to the bottom
            with st.container():
                st.markdown('<div class="footer">', unsafe_allow_html=True)
                
                # Add Species Notes button
                if st.session_state.page != "Species Notes":
                    if st.button("Species Notes", use_container_width=True, key="species_notes"):
                        st.session_state.page = "Species Notes"
                        st.rerun()
                
                # Replace radio with a button for archived trees
                if st.session_state.page != "Graveyard":
                    if st.button("Graveyard", use_container_width=True, key="arkive"):
                        st.session_state.page = "Graveyard"
                        st.rerun()
                
                # Add export button to sidebar
                if state_button("Export Data", key="export", use_container_width=True):
                    with st.spinner("Preparing export..."):
                        try:
                            db = SessionLocal()
                            export_path = export_bonsai_data(db)
                            
                            # Create download button
                            with open(export_path, "rb") as f:
                                st.download_button(
                                    label="Download Export",
                                    data=f,
                                    file_name=os.path.basename(export_path),
                                    mime="application/zip",
                                    key="download_export"
                                )
                            
                            # Clean up zip file after download button is created
                            os.remove(export_path)
                            
                        except Exception as e:
                            st.error(f"Export failed: {str(e)}")
                        finally:
                            db.close()
                st.markdown('</div>', unsafe_allow_html=True)
        finally:
            db.close()
            
    if st.session_state.page == "Settings":
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
        show_settings_form()    

    # Main content
    if st.session_state.page == "View Trees":
        st.header("Bonsai Collection")
        
        if st.button("➕ Add New Tree"):
            st.session_state.page = "Add New Tree"
            st.rerun()
        
        db = SessionLocal()
        try:
            # Query trees with their latest update dates
            trees_with_updates = (
                db.query(
                    Tree,
                    # Get the most recent update date for each tree
                    func.max(TreeUpdate.update_date).label('latest_update')
                )
                .outerjoin(TreeUpdate)  # Outer join to include trees with no updates
                .filter(Tree.is_archived == 0)
                .group_by(Tree.id)
                .order_by(
                    # Sort by latest update date descending, nulls last
                    func.coalesce(func.max(TreeUpdate.update_date), 
                                datetime(1900, 1, 1)).desc()
                )
                .all()
            )
            
            # Extract just the tree objects in the correct order
            trees = [tree for tree, _ in trees_with_updates]
            
            if trees:
                # Create grid layout
                col_count = 4
                cols = st.columns(col_count)
                for idx, tree in enumerate(trees):
                    with cols[idx % col_count]:
                        with st.container():
                            create_tree_card(tree, db)
        finally:
            db.close()
    
    elif st.session_state.page == "Species Notes":
        show_species_notes()
    
    elif st.session_state.page == "Edit Species" and st.session_state.selected_species:
        show_edit_species_form(st.session_state.selected_species)
    
    elif st.session_state.page == "Graveyard":
        # Add back button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        show_graveyard_trees()
    
    elif st.session_state.page == "Add New Tree":
        # Add "Back to Collection" button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        st.header("Add New Tree")
        show_add_tree_form()
    
    elif st.session_state.page == "Update Tree" and st.session_state.selected_tree:
        show_update_form(st.session_state.selected_tree)
    
    elif st.session_state.page == "Tree Gallery" and st.session_state.selected_tree:
        show_tree_gallery(st.session_state.selected_tree)
    
    elif st.session_state.page == "Edit Tree" and st.session_state.selected_tree:
        show_edit_tree_form(st.session_state.selected_tree)
        
    elif st.session_state.page == "Work History" and st.session_state.selected_tree:
        show_work_history(st.session_state.selected_tree)
        
    #button font
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Kdam+Thmor+Pro&family=Roboto:wght@500&display=swap" rel="stylesheet">
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()