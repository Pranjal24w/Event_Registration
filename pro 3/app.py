from flask import Flask, render_template, request, redirect, session, send_file, flash
import mysql.connector
import hashlib
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ===================== DATABASE CONNECTION =====================
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="24Rujal@2005",
    database="college_event2"
)
cursor = db.cursor(dictionary=True)

# ===================== AUTH ROUTES =====================
@app.route('/')
def home():
    return redirect('/login')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Signup for Students only"""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        phone = request.form['phone']
        year = request.form['year']
        department = request.form['department']
        role = 'student'

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            return render_template('signup.html', error="Email already registered!")

        cursor.execute("""
            INSERT INTO users (name, email, password, phone, department, year, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, email, password, phone, department, year, role))
        db.commit()
        return redirect('/login')

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login for all roles"""
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()

        cursor.execute("SELECT * FROM users WHERE email=%s AND password=%s", (email, password))
        user = cursor.fetchone()

        if not user:
            return render_template('login.html', error="Invalid credentials!")

        session['user_id'] = user['user_id']
        session['role'] = user['role']
        session['name'] = user['name']
        session['department'] = user['department']

        # Redirect to dashboards
        if user['role'] == 'student':
            return redirect('/student_dashboard')
        elif user['role'] == 'committee':
            return redirect('/committee_dashboard')
        elif user['role'] == 'faculty':
            return redirect('/faculty_dashboard')
        elif user['role'] == 'hod':
            return redirect('/hod_dashboard')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ===================== STUDENT DASHBOARD =====================
@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'role' not in session or session['role'] != 'student':
        return redirect('/login')

    student_id = session['user_id']

    # ✅ Fetch all available events (with department & host committee)
    cursor.execute("""
        SELECT event_id, event_name, host_committee, department, description, start_date, end_date, fees
        FROM events
        ORDER BY start_date ASC
    """)
    events = cursor.fetchall()

    # ✅ Fetch student's registered events (include dept & committee name)
    cursor.execute("""
        SELECT e.event_name, e.department, e.host_committee, 
               r.payment_status, r.attendance_status
        FROM registrations r
        JOIN events e ON r.event_id = e.event_id
        WHERE r.student_id = %s
    """, (student_id,))
    my_events = cursor.fetchall()

    if request.method == 'POST':
        event_id = request.form['event_id']

        # Prevent duplicate registration
        cursor.execute("""
            SELECT * FROM registrations 
            WHERE student_id = %s AND event_id = %s
        """, (student_id, event_id))
        existing = cursor.fetchone()

        if existing:
            flash('You are already registered for this event!', 'warning')
        else:
            cursor.execute("""
                INSERT INTO registrations (student_id, event_id, payment_status, attendance_status)
                VALUES (%s, %s, 'Unpaid', 'Pending')
            """, (student_id, event_id))
            db.commit()
            flash('Successfully registered for the event!', 'success')

        return redirect('/student_dashboard')

    return render_template(
        'student_dashboard.html',
        events=events,
        my_events=my_events,
        name=session['name']
    )



# ===================== COMMITTEE DASHBOARD =====================
@app.route('/committee_dashboard', methods=['GET', 'POST'])
def committee_dashboard():
    if 'role' not in session or session['role'] != 'committee':
        return redirect('/login')

    committee_name = session['name']           # example: DESOC-CSD
    department = session['department']

    if request.method == 'POST':
        # ADD EVENT
        if 'add_event' in request.form:
            cursor.execute("""
                INSERT INTO events (event_name, host_committee, department, description, start_date, end_date, fees)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                request.form.get('event_name'),
                committee_name,                     # 👈 auto set committee name
                department,                         # 👈 auto set department
                request.form.get('description'),
                request.form.get('start_date'),
                request.form.get('end_date'),
                request.form.get('fees')
            ))
            db.commit()
            flash("New event added successfully!", "success")

        # DELETE EVENT
        elif 'delete_event' in request.form:
            event_id = request.form.get('event_id')
            cursor.execute("""
                DELETE FROM events 
                WHERE event_id = %s AND host_committee = %s
            """, (event_id, committee_name))
            db.commit()
            flash("Event deleted successfully!", "warning")

        # EDIT EVENT
        elif 'edit_event' in request.form:
            event_id = request.form.get('event_id')
            event_name = request.form.get('event_name')
            description = request.form.get('description')
            fees = request.form.get('fees')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')

            cursor.execute("""
                UPDATE events 
                SET event_name = %s, description = %s, fees = %s, start_date = %s, end_date = %s
                WHERE event_id = %s AND host_committee = %s
            """, (event_name, description, fees, start_date, end_date, event_id, committee_name))
            db.commit()
            flash("Event details updated successfully!", "info")

        # TOGGLE PAYMENT STATUS
        elif 'toggle_payment' in request.form:
            student_name = request.form.get('student_name')
            event_name = request.form.get('event_name')
            current_status = request.form.get('current_status')

            new_status = 'Paid' if current_status == 'Unpaid' else 'Unpaid'
            cursor.execute("""
                UPDATE registrations r
                JOIN users u ON r.student_id = u.user_id
                JOIN events e ON r.event_id = e.event_id
                SET r.payment_status = %s
                WHERE u.name = %s AND e.event_name = %s AND e.host_committee = %s
            """, (new_status, student_name, event_name, committee_name))
            db.commit()
            flash(f"Payment status updated to {new_status}!", "success")

        return redirect('/committee_dashboard')

    # ✅ SHOW ONLY EVENTS CREATED BY THIS COMMITTEE
    cursor.execute("""
        SELECT * FROM events
        WHERE host_committee = %s AND department = %s
    """, (committee_name, department))
    events = cursor.fetchall()

    # ✅ SHOW ONLY REGISTRATIONS OF EVENTS FROM THIS COMMITTEE
    cursor.execute("""
        SELECT 
            u.name, 
            u.department, 
            u.year, 
            e.event_name, 
            r.payment_status, 
            r.attendance_status
        FROM registrations r
        JOIN users u ON r.student_id = u.user_id
        JOIN events e ON r.event_id = e.event_id
        WHERE e.host_committee = %s AND e.department = %s
    """, (committee_name, department))
    registrations = cursor.fetchall()

    return render_template('committee_dashboard.html', events=events, registrations=registrations, name=session['name'])


# ===================== FACULTY DASHBOARD =====================  
@app.route('/faculty_dashboard', methods=['GET', 'POST'])
def faculty_dashboard():
    if 'role' not in session or session['role'] != 'faculty':
        return redirect('/login')

    faculty_id = session['user_id']

    # ✅ Handle attendance toggle
    if request.method == 'POST':
        if 'toggle_attendance' in request.form:
            student_name = request.form.get('student_name')
            event_name = request.form.get('event_name')
            current_status = request.form.get('current_status')

            # Toggle logic
            if current_status == 'Pending':
                new_status = 'Present'
            elif current_status == 'Present':
                new_status = 'Absent'
            else:
                new_status = 'Pending'

            cursor.execute("""
                UPDATE registrations r
                JOIN users u ON r.student_id = u.user_id
                JOIN events e ON r.event_id = e.event_id
                SET r.attendance_status = %s
                WHERE u.name = %s AND e.event_name = %s
            """, (new_status, student_name, event_name))
            db.commit()
            flash(f"Attendance updated to {new_status}!", "info")

        return redirect('/faculty_dashboard')

    # ✅ Load only students registered for events assigned to this faculty
    cursor.execute("""
        SELECT 
            r.reg_id, 
            u.name, 
            u.year, 
            u.department, 
            e.event_name, 
            r.payment_status, 
            r.attendance_status
        FROM registrations r
        JOIN users u ON r.student_id = u.user_id
        JOIN events e ON r.event_id = e.event_id
        JOIN faculty_event_access fea ON fea.event_id = e.event_id
        WHERE fea.faculty_id = %s
    """, (faculty_id,))
    data = cursor.fetchall()

    # ✅ Fetch faculty’s assigned events
    cursor.execute("""
        SELECT e.event_name, e.department, e.host_committee
        FROM events e
        JOIN faculty_event_access fea ON e.event_id = fea.event_id
        WHERE fea.faculty_id = %s
    """, (faculty_id,))
    assigned_events = cursor.fetchall()

    # ✅ Faculty personal info
    cursor.execute("""
        SELECT user_id, name, email, phone, department, role
        FROM users
        WHERE user_id = %s
    """, (faculty_id,))
    faculty_details = cursor.fetchone()

    return render_template(
        'faculty_dashboard.html',
        data=data,
        name=session['name'],
        faculty_details=faculty_details,
        assigned_events=assigned_events
    )

# ===================== HOD DASHBOARD =====================
@app.route('/hod_dashboard', methods=['GET', 'POST'])
def hod_dashboard():
    if 'role' not in session or session['role'] != 'hod':
        return redirect('/login')

    dept = session['department']

    # Assign faculty to event
    if request.method == 'POST' and 'assign_faculty' in request.form:
        faculty_id = request.form['faculty_id']
        event_id = request.form['event_id']

        cursor.execute("""
            INSERT INTO faculty_event_access (faculty_id, event_id)
            VALUES (%s, %s)
        """, (faculty_id, event_id))
        db.commit()

    # Fetch events of department
    cursor.execute("""
        SELECT e.event_id, e.event_name, e.department, e.host_committee
        FROM events e
        WHERE e.department=%s
    """, (dept,))
    events = cursor.fetchall()

    # Faculty list
    cursor.execute("SELECT * FROM users WHERE role='faculty' AND department=%s", (dept,))
    faculties = cursor.fetchall()

    # Assigned faculty-event mapping
    cursor.execute("""
        SELECT e.event_name, u.name AS faculty_name
        FROM faculty_event_access fea
        JOIN events e ON fea.event_id = e.event_id
        JOIN users u ON fea.faculty_id = u.user_id
        WHERE e.department=%s
    """, (dept,))
    assignments = cursor.fetchall()

    return render_template('hod_dashboard.html', events=events, faculties=faculties, assignments=assignments, name=session['name'])



# ===================== EXPORT TO EXCEL =====================

@app.route('/export/<role>')
def export(role):
    if 'role' not in session:
        return redirect('/login')

    dept = session.get('department')
    user_name = session.get('name')

    # 🧩 Common base query
    base_query = """
        SELECT 
            u.name AS student_name, 
            u.department, 
            u.year, 
            e.event_name, 
            e.host_committee, 
            r.payment_status, 
            r.attendance_status
        FROM registrations r
        JOIN users u ON r.student_id = u.user_id
        JOIN events e ON r.event_id = e.event_id
    """

    # ===================== COMMITTEE EXPORT =====================
    if role == 'committee':
        # Committees only see their own events
        cursor.execute(base_query + """
            WHERE e.host_committee = %s AND e.department = %s
        """, (user_name, dept))
        file_name = f"{dept}_{user_name}_committee_report.xlsx"

    # ===================== FACULTY EXPORT =====================
    elif role == 'faculty':
        # Faculty can export events assigned to them OR in their department
        cursor.execute(base_query + """
            WHERE (e.faculty_coordinator_id = %s OR e.department = %s)
        """, (session.get('user_id'), dept))
        file_name = f"{dept}_faculty_report.xlsx"

    # ===================== HOD EXPORT =====================
    elif role == 'hod':
        # HOD can export all events in their department
        cursor.execute(base_query + """
            WHERE e.department = %s
        """, (dept,))
        file_name = f"{dept}_hod_report.xlsx"

    else:
        return redirect(f'/{role}_dashboard')

    # ✅ Fetch data and create Excel file
    data = cursor.fetchall()

    if not data:
        flash("No data available to export.", "warning")
        return redirect(f'/{role}_dashboard')

    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name=file_name, as_attachment=True)


# ===================== MAIN =====================
if __name__ == '__main__':
    app.run(debug=True)
