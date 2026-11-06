import json
import os
import re
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

DATA_DIR = "campus_event_data"
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
STUDENTS_FILE = os.path.join(DATA_DIR, "students.json")
REGISTRATIONS_FILE = os.path.join(DATA_DIR, "registrations.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")


def is_valid_email(email):
    """Return True when an email address has a reasonable standard format."""
    email = email.strip()

    if len(email) > 254 or email.count("@") != 1:
        return False

    local_part, domain = email.split("@")

    if not local_part or len(local_part) > 64:
        return False

    # Allow common characters in the part before @, but prevent
    # consecutive dots or punctuation at the beginning/end.
    if not re.fullmatch(r"[A-Za-z0-9]+(?:[._%+-][A-Za-z0-9]+)*", local_part):
        return False

    domain_parts = domain.split(".")
    if len(domain_parts) < 2:
        return False

    # Every domain label must be valid and must not begin or end with a hyphen.
    for part in domain_parts:
        if (
            not part
            or len(part) > 63
            or part.startswith("-")
            or part.endswith("-")
            or not re.fullmatch(r"[A-Za-z0-9-]+", part)
        ):
            return False

    # Require a final alphabetic domain extension of at least 2 characters.
    if not re.fullmatch(r"[A-Za-z]{2,}", domain_parts[-1]):
        return False

    return True

# --- Custom Exceptions ---
class ProjectError(Exception):
    """Base class for project-specific errors."""

class InvalidEventIDError(ProjectError):
    pass

class DuplicateRegistrationError(ProjectError):
    pass

class EventFullError(ProjectError):
    pass

class RegistrationNotFoundError(ProjectError):
    pass

# --- Data Classes ---
class Event:
    def __init__(self, event_id, name, date, venue, max_participants):
        self.event_id = str(event_id).strip()
        self.name = str(name).strip()
        self.date = str(date).strip()
        self.venue = str(venue).strip()
        self.max_participants = int(max_participants)

        # Enforce the rule at the data-model level too, so a past-dated
        # event cannot be created even if another part of the app bypasses
        # the Streamlit date picker.
        try:
            event_day = datetime.strptime(self.date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid event date. Please use YYYY-MM-DD format.")

        if event_day < datetime.now().date():
            raise ValueError(
                "Event date cannot be in the past. Please select today or a future date."
            )

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "name": self.name,
            "date": self.date,
            "venue": self.venue,
            "max_participants": self.max_participants,
        }

class Student:
    def __init__(self, student_id, name, email):
        self.student_id = str(student_id).strip()
        self.name = str(name).strip()
        self.email = str(email).strip()

    def to_dict(self):
        return {
            "student_id": self.student_id,
            "name": self.name,
            "email": self.email,
        }

class Registration:
    def __init__(self, event_id, student_id):
        self.event_id = str(event_id).strip()
        self.student_id = str(student_id).strip()
        self.registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "student_id": self.student_id,
            "registered_at": self.registered_at,
        }

# --- Manager Class ---
class CampusEventManager:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.events = self.load_data(EVENTS_FILE)
        self.students = self.load_data(STUDENTS_FILE)
        self.registrations = self.load_data(REGISTRATIONS_FILE)
        self.feedback = self.load_data(FEEDBACK_FILE)

    @staticmethod
    def load_data(filename):
        if not os.path.exists(filename):
            return []
        try:
            with open(filename, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def save_data(filename, data):
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

    def save_all(self):
        self.save_data(EVENTS_FILE, self.events)
        self.save_data(STUDENTS_FILE, self.students)
        self.save_data(REGISTRATIONS_FILE, self.registrations)
        self.save_data(FEEDBACK_FILE, self.feedback)

    def get_event(self, event_id):
        event = next(
            (e for e in self.events if e["event_id"] == str(event_id).strip()),
            None,
        )
        if event is None:
            raise InvalidEventIDError(f"Event ID '{event_id}' does not exist.")
        return event

    def registered_count(self, event_id):
        return sum(1 for r in self.registrations if r["event_id"] == str(event_id))

# Initialize app session state
if "manager" not in st.session_state:
    st.session_state.manager = CampusEventManager()

manager = st.session_state.manager

# --- Streamlit UI Layout ---
st.set_page_config(page_title="Campus Event Management", layout="wide")
st.title("🎓 Campus Event Management & Feedback Analyzer")

menu = [
    "View All Events",
    "Create Event",
    "Register Student",
    "Search Registered Students",
    "Cancel Registration",
    "Collect Feedback",
    "Participation Summary",
    "Analyze Feedback",
    "Generate Charts"
]

choice = st.sidebar.selectbox("Navigation", menu)

# --- 1. View All Events ---
if choice == "View All Events":
    st.subheader("📋 All Campus Events")
    if not manager.events:
        st.info("No events found.")
    else:
        event_list = []
        for event in manager.events:
            count = manager.registered_count(event["event_id"])
            event_list.append({
                "Event ID": event["event_id"],
                "Name": event["name"],
                "Date": event["date"],
                "Venue": event["venue"],
                "Participants": f"{count}/{event['max_participants']}"
            })
        st.dataframe(pd.DataFrame(event_list), use_container_width=True)

# --- 2. Create Event ---
elif choice == "Create Event":
    st.subheader("➕ Create a New Event")
    today = datetime.now().date()
    with st.form("create_event_form"):
        event_id = st.text_input("Event ID").strip()
        name = st.text_input("Event Name").strip()
        # Past dates can be selected so the app can show a clear error
        # after submission. The validation below prevents saving them.
        event_date = st.date_input(
            "Event Date",
            value=today,
        )
        date = event_date.strftime("%Y-%m-%d")
        venue = st.text_input("Venue").strip()
        max_participants = st.number_input("Maximum Participants", min_value=1, value=50)
        submitted = st.form_submit_button("Create Event")

        if submitted:
            try:
                # Server-side validation: reject past event dates as well.
                if datetime.strptime(date, "%Y-%m-%d").date() < datetime.now().date():
                    raise ValueError("Event date cannot be in the past. Please select today or a future date.")

                if not event_id:
                    raise ValueError("Event ID cannot be empty.")
                if any(e["event_id"] == event_id for e in manager.events):
                    raise ValueError("An event with this ID already exists.")
                if not name or not venue:
                    raise ValueError("Event name and venue cannot be empty.")

                event = Event(event_id, name, date, venue, max_participants)
                manager.events.append(event.to_dict())
                manager.save_all()
                st.success(f'Event "{name}" created successfully!')
            except Exception as e:
                st.error(f"Error: {e}")

# --- 3. Register Student ---
elif choice == "Register Student":
    st.subheader("📝 Register Student for Event")
    if not manager.events:
        st.warning("No events available to register for.")
    else:
        event_options = {e["event_id"]: f"{e['name']} ({e['event_id']})" for e in manager.events}
        selected_event_id = st.selectbox("Select Event", options=list(event_options.keys()), format_func=lambda x: event_options[x])
        
        with st.form("register_form"):
            student_id = st.text_input("Student ID").strip()
            student_name = st.text_input("Student Name").strip()
            student_email = st.text_input("Student Email").strip()
            reg_submitted = st.form_submit_button("Register")

            if reg_submitted:
                try:
                    event = manager.get_event(selected_event_id)
                    if not student_id or not student_name or not student_email:
                        raise ValueError("Student ID, name, and email cannot be empty.")

                    if not is_valid_email(student_email):
                        raise ValueError(
                            "Please enter a valid email address (e.g., student@gmail.com)."
                        )

                    if any(r["event_id"] == selected_event_id and r["student_id"] == student_id for r in manager.registrations):
                        raise DuplicateRegistrationError("This student is already registered for this event.")

                    if manager.registered_count(selected_event_id) >= event["max_participants"]:
                        raise EventFullError("This event is full. Registration is closed.")

                    existing_student = next((s for s in manager.students if s["student_id"] == student_id), None)
                    if not existing_student:
                        student = Student(student_id, student_name, student_email).to_dict()
                        manager.students.append(student)

                    registration = Registration(selected_event_id, student_id)
                    manager.registrations.append(registration.to_dict())
                    manager.save_all()
                    st.success(f'Student registered successfully for "{event["name"]}"!')
                except Exception as e:
                    st.error(f"Error: {e}")

# --- 4. Search Registered Students ---
elif choice == "Search Registered Students":
    st.subheader("🔍 Search Registered Students")
    if not manager.events:
        st.info("No events found.")
    else:
        event_options = {e["event_id"]: f"{e['name']} ({e['event_id']})" for e in manager.events}
        selected_event_id = st.selectbox("Select Event", options=list(event_options.keys()), format_func=lambda x: event_options[x])
        
        if st.button("Show Registered Students"):
            matches = [r for r in manager.registrations if r["event_id"] == selected_event_id]
            if not matches:
                st.info("No students are registered for this event.")
            else:
                student_rows = []
                for r in matches:
                    student = next((s for s in manager.students if s["student_id"] == r["student_id"]), None)
                    if student:
                        student_rows.append({
                            "Student ID": student["student_id"],
                            "Name": student["name"],
                            "Email": student["email"],
                            "Registered At": r["registered_at"]
                        })
                st.dataframe(pd.DataFrame(student_rows), use_container_width=True)

# --- 5. Cancel Registration ---
elif choice == "Cancel Registration":
    st.subheader("❌ Cancel Registration")
    event_id_input = st.text_input("Event ID").strip()
    student_id_input = st.text_input("Student ID").strip()

    if st.button("Cancel Registration"):
        try:
            manager.get_event(event_id_input)
            registration = next(
                (r for r in manager.registrations if r["event_id"] == event_id_input and r["student_id"] == student_id_input),
                None
            )
            if registration is None:
                raise RegistrationNotFoundError("No matching registration was found.")

            manager.registrations.remove(registration)
            manager.save_all()
            st.success("Registration cancelled successfully.")
        except Exception as e:
            st.error(f"Error: {e}")

# --- 6. Collect Feedback ---
elif choice == "Collect Feedback":
    st.subheader("⭐ Collect Event Feedback")
    with st.form("feedback_form"):
        event_id_fb = st.text_input("Event ID").strip()
        student_id_fb = st.text_input("Student ID").strip()
        rating = st.slider("Rating (1 to 5)", 1, 5, 5)
        comment = st.text_area("Comment (optional)").strip()
        fb_submitted = st.form_submit_button("Submit Feedback")

        if fb_submitted:
            try:
                manager.get_event(event_id_fb)
                is_registered = any(r["event_id"] == event_id_fb and r["student_id"] == student_id_fb for r in manager.registrations)
                if not is_registered:
                    raise RegistrationNotFoundError("Only a currently registered student can submit feedback.")

                if any(f["event_id"] == event_id_fb and f["student_id"] == student_id_fb for f in manager.feedback):
                    raise ValueError("This student has already submitted feedback.")

                manager.feedback.append({
                    "event_id": event_id_fb,
                    "student_id": student_id_fb,
                    "rating": rating,
                    "comment": comment,
                    "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                manager.save_all()
                st.success("Thank you! Feedback saved successfully.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- 7. Participation Summary ---
elif choice == "Participation Summary":
    st.subheader("📊 Event Participation Summary")
    if not manager.events:
        st.info("No events available.")
    else:
        rows = [{
            "Event ID": e["event_id"],
            "Event Name": e["name"],
            "Date": e["date"],
            "Venue": e["venue"],
            "Participants": manager.registered_count(e["event_id"]),
            "Maximum Participants": e["max_participants"]
        } for e in manager.events]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

# --- 8. Analyze Feedback ---
elif choice == "Analyze Feedback":
    st.subheader("📈 Feedback & Participation Analysis")
    if not manager.feedback:
        st.info("No feedback has been collected yet.")
    else:
        feedback_df = pd.DataFrame(manager.feedback)
        feedback_df["rating"] = pd.to_numeric(feedback_df["rating"], errors="coerce")
        feedback_df = feedback_df.dropna(subset=["rating"])

        event_names = {e["event_id"]: e["name"] for e in manager.events}
        feedback_df["event_name"] = feedback_df["event_id"].map(event_names).fillna(feedback_df["event_id"])

        overall_average = feedback_df["rating"].mean()
        st.metric("Total Feedback Responses", len(feedback_df))
        st.metric("Overall Average Rating", f"{overall_average:.2f} / 5")

        ratings_by_event = feedback_df.groupby("event_name")["rating"].agg(["mean", "count"]).rename(columns={"mean": "Average Rating", "count": "Responses"}).round(2)
        
        st.markdown("### Event-wise Feedback")
        st.dataframe(ratings_by_event, use_container_width=True)

# --- 9. Generate Charts ---
elif choice == "Generate Charts":
    st.subheader("📊 Visual Analytics")
    if not manager.events:
        st.warning("Create at least one event before generating charts.")
    else:
        event_names = [e["name"] for e in manager.events]
        participant_counts = [manager.registered_count(e["event_id"]) for e in manager.events]

        if manager.feedback:
            feedback_df = pd.DataFrame(manager.feedback)
            feedback_df["rating"] = pd.to_numeric(feedback_df["rating"], errors="coerce").dropna()
            name_map = {e["event_id"]: e["name"] for e in manager.events}
            feedback_df["event_name"] = feedback_df["event_id"].map(name_map)
            average_ratings = feedback_df.groupby("event_name")["rating"].mean()

            if not average_ratings.empty:
                st.markdown("### Average Feedback Rating by Event")
                fig, ax = plt.subplots(figsize=(8, 4))
                average_ratings.plot(kind="bar", ax=ax, color="skyblue")
                ax.set_ylabel("Average Rating (out of 5)")
                ax.set_ylim(0, 5)
                plt.xticks(rotation=30, ha="right")
                st.pyplot(fig)

            if not feedback_df.empty:
                st.markdown("### Distribution of Feedback Ratings")
                fig, ax = plt.subplots(figsize=(6, 4))
                ax.hist(feedback_df["rating"], bins=[0.5, 1.5, 2.5, 3.5, 4.5, 5.5], edgecolor="black", rwidth=0.85, color="orange")
                ax.set_xlabel("Rating")
                ax.set_ylabel("Number of Responses")
                ax.set_xticks([1, 2, 3, 4, 5])
                st.pyplot(fig)

        st.markdown("### Event-wise Participation")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(event_names, participant_counts, color="green")
        ax.set_ylabel("Number of Participants")
        plt.xticks(rotation=30, ha="right")
        st.pyplot(fig)