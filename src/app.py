# PYTHONPATH=. streamlit run src/app.py
# src/app.py
import streamlit as st
from src.database import get_db, SessionLocal
from src.models import Tree, TreeUpdate, Photo, Reminder, Species, Settings
from sqlalchemy import func, desc
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
            "Current Girth (cm)": t["current_girth"],
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
                    "Girth (cm)": update["girth"],
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
    """Display work history, girth measurements, and reminders for a specific tree"""
    db = SessionLocal()
    try:
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        # Back button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        st.header(f"Work History: {tree.tree_name} ({tree.tree_number})")
        
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
                    'date': update.update_date.strftime('%Y-%m-%d'),
                    'girth': update.girth
                } for update in measurements]
                
                # Create chart using Streamlit
                import plotly.express as px
                df = pd.DataFrame(data)
                fig = px.line(df, x='date', y='girth', 
                    title='Trunk Girth Over Time (cm)',
                    markers=True)
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
        
        # Work History List
        st.subheader("Work History")
        updates = db.query(TreeUpdate).filter(
            TreeUpdate.tree_id == tree_id
        ).order_by(TreeUpdate.update_date.desc()).all()
        
        if updates:
            for update in updates:
                with st.container():
                    # Date and work description
                    st.markdown(f"**{update.update_date.strftime('%Y-%m-%d')}**")
                    st.write(update.work_performed)
                    
                    # Show girth measurement if available
                    if update.girth:
                        st.write(f"*Trunk Width: {update.girth} cm*")
                    
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
        with st.expander(f"**{tree.tree_name}**  \n*({tree.tree_number})*", expanded=False):
            # Make buttons more touch-friendly on mobile
            button_cols = st.columns([1, 1, 1])
            
            with button_cols[0]:
                if st.button("Gallery", key=f"gallery_{tree.id}", use_container_width=True):
                    st.session_state.page = "Tree Gallery"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            with button_cols[1]:
                if st.button("History", key=f"work_history_{tree.id}", use_container_width=True):
                    st.session_state.page = "Work History"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            with button_cols[2]:
                if st.button("Add Update", key=f"update_{tree.id}", use_container_width=True):
                    st.session_state.page = "Update Tree"
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
                st.write(f"**Last Update ({latest_update.update_date.strftime('%Y-%m-%d')})**\n\n{latest_update.work_performed}")
            
            # Action buttons in a single row
            col1, col2, col3 = st.columns([2, 3, 2])
            with col1:
                if st.button(f"Edit", key=f"edit_{tree.id}", use_container_width=True):
                    st.session_state.page = "Edit Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            with col3:
                if st.button("Archive", key=f"archive_{tree.id}", use_container_width=True):
                    tree.is_archived = 1
                    db.commit()
                    st.success(f"Tree {tree.tree_number} archived successfully!")
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
        
        
        
        st.header(f"Gallery: {tree.species_info.name} ({tree.tree_number})")
            
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
                tree_galler_grid = grid([8,1],1,[10,2,2])
                if os.path.exists(photo.file_path):
                    tree_galler_grid.write("")
                    # Create a unique key for each photo's container
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
                            key=f"date_input_{photo.id}"
                        )
                        
                        # Save button
                        if st.button("Save", key=f"save_{photo.id}"):
                            photo.photo_date = datetime.combine(new_date, datetime.min.time())
                            db.commit()
                            st.session_state[edit_key] = False
                            st.rerun()
                        
                        # Cancel button
                        if st.button("Cancel", key=f"cancel_{photo.id}"):
                            st.session_state[edit_key] = False
                            st.rerun()
                    else:
                        # Display current date when not in edit mode
                        tree_galler_grid.write(f"Date: {photo.photo_date.strftime('%Y-%m-%d')}")
                    

                    if tree_galler_grid.button("Edit Date", key=f"edit_button_{photo.id}"):
                        st.session_state[f"edit_mode_{photo.id}"] = True
                        st.rerun()
                    

                    # Delete button and confirmation handling
                    delete_key = f"confirm_delete_{photo.id}"
                    if delete_key not in st.session_state:
                        st.session_state[delete_key] = False
                    
                    if not st.session_state[delete_key]:
                        if tree_galler_grid.button("Delete", key=f"delete_{photo.id}"):
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
                    
                    # Add a separator between photos
                    st.markdown("---")
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
                    "New Trunk Width (cm)", 
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
                current_girth = st.number_input("Current Girth (cm)", 
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

def show_archived_trees():
    """Display archived trees with option to delete"""
    st.header("Archived Trees")
    
    db = SessionLocal()
    try:
        archived_trees = db.query(Tree).filter(Tree.is_archived == 1).all()
        
        if not archived_trees:
            st.info("No archived trees found.")
            return
        
        for tree in archived_trees:
            with st.container():
                col1, col2, col3 = st.columns([6, 2, 2])
                
                with col1:
                    st.write(f"**{tree.tree_name}** ({tree.tree_number})")
                    st.write(f"Species: {tree.species_info.name}")
                
                with col2:
                    if st.button("Restore", key=f"restore_{tree.id}"):
                        tree.is_archived = 0
                        db.commit()
                        st.success(f"Tree {tree.tree_number} restored!")
                        st.rerun()
                
                with col3:
                    if st.button("Delete", key=f"delete_{tree.id}"):
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
                
                if st.form_submit_button("Save Settings"):
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
            
            # Use custom logo if it exists and is valid
            if settings.sidebar_image and os.path.exists(settings.sidebar_image):
                st.image(settings.sidebar_image, use_container_width=True)
            else:
                # Fallback to default logo
                st.image("C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png", width=125)
            
            # Use custom title
            st.title(settings.app_title)
            
            


        # Create a container to push buttons to the bottom
            with st.container():
                st.markdown('<div class="footer">', unsafe_allow_html=True)
            
                # Replace radio with a button for archived trees
                if st.session_state.page != "Archived Trees":
                    if st.button("View Archive", use_container_width=True):
                        st.session_state.page = "Archived Trees"
                        st.rerun()
                    

                # Add export button to sidebar
                if state_button("Export Data", key="export",use_container_width=True):
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
                                    mime="application/zip"
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
        st.header("Your Bonsai Collection")
        
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
    
    elif st.session_state.page == "Archived Trees":
        # Add back button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
            
        show_archived_trees()
    
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