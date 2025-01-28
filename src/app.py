# src/app.py
import streamlit as st
from src.database import get_db, SessionLocal
from src.models import Tree, TreeUpdate, Photo, Reminder, Species
from datetime import datetime
import os
from PIL import Image

# Set page config
st.set_page_config(page_title="Bonsai Tracker", layout="wide")

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

def main():
    st.title("Bonsai Tracker")
    
    # Sidebar navigation
    page = st.sidebar.selectbox("Navigate", ["View Trees", "Add New Tree"])
    
    if page == "Add New Tree":
        st.header("Add New Tree")
        
        # Get existing species list
        db = SessionLocal()
        existing_species = get_existing_species(db)
        db.close()
        
        with st.form(key="new_tree_form", clear_on_submit=True):
            # Get a new tree number (display only)
            db = SessionLocal()
            new_tree_number = generate_tree_number(db)
            db.close()
            
            st.info(f"Tree Number will be: {new_tree_number}")
            
            # Species selection with "Add New" option
            species_options = ["Add New Species"] + existing_species
            species_selection = st.selectbox(
                "Species*",
                options=species_options,
                index=len(species_options)-1 if existing_species else 0,
                help="Select existing species or add new one"
            )
            
            # Show text input if "Add New Species" is selected
            if species_selection == "Add New Species":
                new_species = st.text_input(
                    "Enter New Species Name*",
                    help="Enter the botanical or common name of your tree"
                )
                species = new_species
            else:
                species = species_selection
            
            # Rest of the form
            col1, col2 = st.columns(2)
            
            with col1:
                current_girth = st.number_input("Current Girth (cm)", 
                    min_value=0.0, step=0.1)
                current_height = st.number_input("Current Height (cm)", 
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
                if not species:
                    st.error("Species is required!")
                    return
                
                try:
                    db = SessionLocal()
                    
                    # Get or create species
                    species_obj = get_or_create_species(db, species)
                    
                    # Create new tree
                    new_tree = Tree(
                        tree_number=generate_tree_number(db),
                        species_id=species_obj.id,
                        date_acquired=datetime.combine(date_acquired, datetime.min.time()),
                        origin_date=datetime.combine(origin_date, datetime.min.time()),
                        current_girth=current_girth,
                        current_height=current_height,
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
                    
                except Exception as e:
                    st.error(f"Error adding tree: {str(e)}")
                finally:
                    db.close()

    elif page == "View Trees":
        st.header("Your Trees")
        db = SessionLocal()
        try:
            trees = db.query(Tree).all()
            if not trees:
                st.info("No trees added yet. Use the 'Add New Tree' page to get started!")
            else:
                for tree in trees:
                    with st.expander(f"Tree #{tree.tree_number} - {tree.species_info.name}"):
                        st.write(f"Training Age: {tree.training_age:.1f} years")
                        st.write(f"True Age: {tree.true_age:.1f} years")
                        st.write(f"Current Measurements: {tree.current_height}cm tall, {tree.current_girth}cm girth")
                        if tree.notes:
                            st.write("Notes:", tree.notes)
                        
                        latest_photo = db.query(Photo).filter(Photo.tree_id == tree.id).order_by(Photo.photo_date.desc()).first()
                        if latest_photo and os.path.exists(latest_photo.file_path):
                            st.image(latest_photo.file_path, caption="Most recent photo", width=300)
        except Exception as e:
            st.error(f"Error loading trees: {str(e)}")
        finally:
            db.close()

if __name__ == "__main__":
    main()