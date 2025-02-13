# PYTHONPATH=. streamlit run src/app.py
# src/app.py
import streamlit as st
from src.database import get_db, SessionLocal
from src.models import Tree, TreeUpdate, Photo, Reminder, Species
from datetime import datetime
import os
import pandas as pd
from PIL import Image
import PIL.ExifTags
import glob

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

def save_uploaded_image(uploaded_file):
    """Save uploaded image to the images directory"""
    image_dir = os.path.join('data', 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_extension = os.path.splitext(uploaded_file.name)[1]
    filename = f"tree_{timestamp}{file_extension}"
    
    file_path = os.path.join(image_dir, filename)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    return file_path

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
                if st.button(f"✏️ Edit", key=f"edit_{tree.id}", use_container_width=True):
                    st.session_state.page = "Edit Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            with button_cols[1]:
                if st.button("📦 Archive", key=f"archive_{tree.id}", use_container_width=True):
                    tree.is_archived = 1
                    db.commit()
                    st.success(f"Tree {tree.tree_number} archived successfully!")
                    st.rerun()
            
            with button_cols[2]:
                if st.button("📁 History", key=f"work_history_{tree.id}", use_container_width=True):
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
                st.image(display_photo.file_path, use_column_width=True)
            else:
                st.image("https://via.placeholder.com/150", use_column_width=True)
            
            # Rest of the card content...
            if tree.notes:
                st.write("**Note:**", tree.notes)
            
            latest_update = db.query(TreeUpdate).filter(
                TreeUpdate.tree_id == tree.id
            ).order_by(TreeUpdate.update_date.desc()).first()
            
            if latest_update:
                st.write("**Last Update:**", latest_update.work_performed)
                st.write(f"**Updated:** {latest_update.update_date.strftime('%Y-%m-%d')}")
            
            # Action buttons in a single row
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Add Update", key=f"update_{tree.id}"):
                    st.session_state.page = "Update Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            with col2:
                if st.button("Tree Gallery", key=f"gallery_{tree.id}"):
                    st.session_state.page = "Tree Gallery"
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
        
        col1, col2, col3 = st.columns([1, 6, 2])
        with col2:
            st.header(f"Gallery: {tree.species_info.name} ({tree.tree_number})")
            
            photos = db.query(Photo).filter(
                Photo.tree_id == tree_id
            ).order_by(Photo.photo_date).all()
            
            # No photos message
            if not photos:
                st.info("No photos available for this tree.")
                return
            
            # Photo display loop
            for photo in photos:
                if os.path.exists(photo.file_path):
                    # Create a unique key for each photo's container
                    with st.container():
                        # Display the image
                        st.image(photo.file_path, use_column_width=True)
                        
                        # Create columns for date display and action buttons
                        date_col, edit_col, star_col, delete_col = st.columns([8, 1, 1, 1])
                        
                        with date_col:
                            # Initialize session state for edit mode
                            edit_key = f"edit_mode_{photo.id}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = False
                            
                            if st.session_state[edit_key]:
                                # Show date input when in edit mode
                                new_date = st.date_input(
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
                                st.write(f"Date: {photo.photo_date.strftime('%Y-%m-%d')}")
                        
                        with edit_col:
                            # Edit button
                            if st.button("✏️", key=f"edit_button_{photo.id}"):
                                st.session_state[f"edit_mode_{photo.id}"] = True
                                st.rerun()
                        
                        with star_col:
                            # Star/unstar button
                            star_icon = "⭐" if photo.is_starred else "☆"
                            if st.button(star_icon, key=f"star_{photo.id}"):
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
                        
                        with delete_col:
                            # Delete button and confirmation handling
                            delete_key = f"confirm_delete_{photo.id}"
                            if delete_key not in st.session_state:
                                st.session_state[delete_key] = False
                            
                            if not st.session_state[delete_key]:
                                if st.button("🗑️", key=f"delete_{photo.id}"):
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

def main():
    st.set_page_config(page_title="Bonsai Tracker", layout="wide", initial_sidebar_state="auto")
    
    with open('C:\\Users\\loudo\\Desktop\\bonsai-tracker\\src\\style.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = "View Trees"
    if 'selected_tree' not in st.session_state:
        st.session_state.selected_tree = None
    
    # Sidebar
    with st.sidebar:
        st.image("C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png", width=100)
        st.title("Bonsai Tracker")
        
        # Replace radio with a button for archived trees
        if st.session_state.page != "Archived Trees":
            if st.button("📦"):
                st.session_state.page = "Archived Trees"
                st.rerun()
    
    st.title("Bonsai Tracker")
    
    # Main content
    if st.session_state.page == "View Trees":
        st.header("Your Bonsai Collection")
        
        if st.button("➕ Add New Tree"):
            st.session_state.page = "Add New Tree"
            st.rerun()
        
        db = SessionLocal()
        try:
            trees = db.query(Tree).filter(Tree.is_archived == 0).all()
            
            if trees:
                # Alternative approach using Streamlit's built-in responsive layout
                col_count = 4  # Maximum number of columns
                cols = st.columns(col_count)
                for idx, tree in enumerate(trees):
                    with cols[idx % col_count]:
                        # Make the card container responsive
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

if __name__ == "__main__":
    main()