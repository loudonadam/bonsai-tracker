import streamlit as st
import pandas as pd
from datetime import date, datetime
from PIL import Image
import os
from database import add_bonsai_tree, get_session, BonsaiTree
import sys

def main():
    st.title("Bonsai Tracker")
    
    # Sidebar navigation
    page = st.sidebar.selectbox(
        "Select Page",
        ["View Collection", "Add New Tree", "Tree Updates"]
    )
    
    if page == "Add New Tree":
        show_add_tree_page()
    elif page == "View Collection":
        show_collection_page()
    elif page == "Tree Updates":
        show_updates_page()

def show_add_tree_page():
    st.header("Add New Bonsai Tree")
    
    with st.form("add_tree_form"):
        # Basic Information
        col1, col2 = st.columns(2)
        with col1:
            tree_number = st.text_input("Tree Number")
            species = st.text_input("Species")
            girth = st.number_input("Girth (mm)", min_value=0)
            height = st.number_input("Height (mm)", min_value=0)
        
        with col2:
            origin_date = st.date_input("Origin Date")
            date_acquired = st.date_input("Date Acquired")
            special_notes = st.text_area("Special Notes")
        
        # Image Upload
        uploaded_file = st.file_uploader("Upload Tree Image", type=['png', 'jpg', 'jpeg'])
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Image", use_column_width=True)
            
            # Extract metadata if available
            metadata = extract_image_metadata(image)
            if metadata:
                st.info(f"Photo taken on: {metadata['date']}")
        
        # Submit button
        submitted = st.form_submit_button("Add Tree")
        
        if submitted:
            try:
                # Save image if uploaded
                image_path = None
                if uploaded_file:
                    # Ensure directory exists
                    os.makedirs('data/images', exist_ok=True)
                    
                    # Generate filename and save
                    filename = generate_image_filename(tree_number, metadata if metadata else {'date': date.today()})
                    image_path = os.path.join('data', 'images', filename)
                    image.save(image_path)
                
                # Add tree to database
                tree_id = add_bonsai_tree(
                    tree_number=tree_number,
                    species=species,
                    girth=girth,
                    height=height,
                    date_acquired=date_acquired,
                    origin_date=origin_date,
                    image_path=image_path,
                    special_notes=special_notes
                )
                
                if tree_id:
                    st.success("Tree added successfully!")
                    # Clear form (Streamlit will naturally clear on rerun)
                else:
                    st.error("Failed to add tree")
                    
            except Exception as e:
                st.error(f"An error occurred: {e}")

def show_collection_page():
    st.header("Bonsai Collection")
    
    # Get all trees from database
    session = get_session()
    trees = session.query(BonsaiTree).all()
    
    if not trees:
        st.info("No trees in collection yet.")
        return
    
    # Display trees in grid
    cols = st.columns(3)
    for idx, tree in enumerate(trees):
        with cols[idx % 3]:
            # Show tree card
            with st.container():
                if tree.current_image_path and os.path.exists(tree.current_image_path):
                    st.image(tree.current_image_path, caption=f"Tree {tree.tree_number}")
                
                st.write(f"**Species:** {tree.species}")
                st.write(f"**Age:** {tree.total_age} years")
                st.write(f"**Training Age:** {tree.age_in_training} years")
                
                if st.button(f"View Details #{tree.tree_number}"):
                    st.session_state.selected_tree = tree.id
                    # You would handle navigation to detail view here

def show_updates_page():
    st.header("Tree Updates")
    # Implementation for updates page
    st.info("Updates page coming soon!")

if __name__ == "__main__":
    main()