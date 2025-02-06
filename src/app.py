# PYTHONPATH=. streamlit run src/app.py
# src/app.py
import streamlit as st
from src.database import get_db, SessionLocal
from src.models import Tree, TreeUpdate, Photo, Reminder, Species
from datetime import datetime
import os
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

def create_tree_card(tree, db):
    """Create a card display for a single tree with edit functionality"""
    with st.container():
        # Use expander for the card-like effect
        with st.expander(f"**{tree.tree_name}**  \n*({tree.tree_number})*", expanded=False):
            # Create a row with tree name and edit button
            col1, col2 = st.columns([5, 2])
            with col1:
                # Placeholder for tree details
                st.write("")
            
            with col2:
                # Edit button with pencil icon
                if st.button(f"✏️", key=f"edit_{tree.id}",use_container_width=True):
                    st.session_state.page = "Edit Tree"
                    st.session_state.selected_tree = tree.id
                    st.rerun()
            
            # Display the latest photo
            latest_photo = db.query(Photo).filter(
                Photo.tree_id == tree.id
            ).order_by(Photo.photo_date.desc()).first()
            
            if latest_photo and os.path.exists(latest_photo.file_path):
                st.image(latest_photo.file_path, width=200, use_column_width=True)
            else:
                st.image("https://via.placeholder.com/150", width=200)
            
            # Display tree information
            if tree.notes:
                st.write("**Note:**", tree.notes)
            
            latest_update = db.query(TreeUpdate).filter(
                TreeUpdate.tree_id == tree.id
            ).order_by(TreeUpdate.update_date.desc()).first()
            
            if latest_update:
                st.write("**Last Update:**", latest_update.work_performed)
                st.write(f"**Updated:** {latest_update.update_date.strftime('%Y-%m-%d')}")
            
            # Action buttons in a single row
            st.button("Add Update", key=f"update_{tree.id}", 
                on_click=lambda: set_page_and_tree('Update Tree', tree.id))
            
            st.button("Tree Gallery", key=f"gallery_{tree.id}", 
                on_click=lambda: set_page_and_tree('Tree Gallery', tree.id))

def set_page_and_tree(page, tree_id=None):
    """Helper function to set both page and selected tree"""
    st.session_state.page = page
    st.session_state.selected_tree = tree_id
    
def show_tree_gallery(tree_id):
    """Display gallery view for a specific tree"""
    db = SessionLocal()
    try:
        tree = db.query(Tree).filter(Tree.id == tree_id).first()
        
        # Add "Back to Collection" button at the top
        if st.button("← Back to Collection"):
            st.session_state.page = "View Trees"
            st.rerun()
        
        col1, col2, col3 = st.columns([1, 6, 2])
        with col2:
            
            st.header(f"Gallery: {tree.species_info.name} ({tree.tree_number})")
            
            photos = db.query(Photo).filter(
                Photo.tree_id == tree_id
            ).order_by(Photo.photo_date).all()
            
            col1, col2, col3 = st.columns([1, 5, 3])
            with col2:
                for photo in photos:
                    if os.path.exists(photo.file_path):
                        st.image(photo.file_path, caption=f"Date: {photo.photo_date.strftime('%Y-%m-%d')}",
                                use_column_width=True)
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
            current_girth = st.number_input("New Trunk Width (cm)", 
                value=tree.current_girth if tree.current_girth else 0.0,
                step=0.1)
            
            work_description = st.text_area("Work Performed")
            
            uploaded_files = st.file_uploader("Add Photos", 
                type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
            
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
                
                # Create tree update
                update = TreeUpdate(
                    tree_id=tree_id,
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
    st.set_page_config(page_title="Bonsai Tracker", layout="wide", initial_sidebar_state="collapsed")
    
    with open('C:\\Users\\loudo\\Desktop\\bonsai-tracker\\src\\style.css') as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.image("C:\\Users\\loudo\\Desktop\\Bonsai Design\\Screenshot+2020-01-29+at+10.52.32+AM.png", width=100)  # Add your logo
        st.title("Bonsai Tracker")
    
    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = "View Trees"
    if 'selected_tree' not in st.session_state:
        st.session_state.selected_tree = None
    
    st.title("Bonsai Tracker")
    
    # Main content
    if st.session_state.page == "View Trees":
        st.header("Your Bonsai Collection")
        
        # Add New Tree button at the top
        if st.button("➕ Add New Tree"):
            st.session_state.page = "Add New Tree"
            st.rerun()
        
        db = SessionLocal()
        try:
            trees = db.query(Tree).all()
            
            # Create grid layout
            if trees:
                cols = st.columns(4)
                for idx, tree in enumerate(trees):
                    with cols[idx % 4]:
                        create_tree_card(tree, db)
        finally:
            db.close()
    
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

if __name__ == "__main__":
    main()