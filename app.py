import os
from dotenv import load_dotenv
from openpyxl import Workbook
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from markupsafe import Markup
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import secrets
import string
from reportlab.lib import colors
import csv
import secrets
import string
from io import BytesIO, StringIO
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'your-secret-key-here'

# Database Configuration - Using pymysql for Windows compatibility
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/hr_system_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True

# Initialize database
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Models
class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    location = db.Column(db.String(100))
    budget = db.Column(db.Numeric(15, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Explicitly specify foreign_keys for relationships
    manager = db.relationship('Employee', foreign_keys=[manager_id], backref='managed_departments')

class Position(db.Model):
    __tablename__ = 'positions'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    min_salary = db.Column(db.Numeric(15, 2))
    max_salary = db.Column(db.Numeric(15, 2))
    
    department = db.relationship('Department', backref='positions')

class Employee(db.Model):
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    hire_date = db.Column(db.Date, nullable=False)
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'))
    salary = db.Column(db.Numeric(15, 2))
    manager_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    status = db.Column(db.String(20), default='active')
    password = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Explicitly specify foreign_keys for all relationships
    position = db.relationship('Position', backref='employees')
    manager = db.relationship('Employee', remote_side=[id], backref='subordinates')
    department = db.relationship('Department', foreign_keys=[department_id], backref='department_employees')

class Attendance(db.Model):
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_by = db.Column(db.Integer, db.ForeignKey('employees.id'))
    approved_at = db.Column(db.DateTime)

    # new code
    check_in_location = db.Column(db.String(100))  # Latitude,Longitude
    check_out_location = db.Column(db.String(100))
    device_info = db.Column(db.String(100))  # Mobile device details
    ip_address = db.Column(db.String(50))
    is_remote = db.Column(db.Boolean, default=False)
    
    employee = db.relationship('Employee', foreign_keys=[employee_id], backref='attendances')
    approver = db.relationship('Employee', foreign_keys=[approved_by])

class Leave(db.Model):
    __tablename__ = 'leaves'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='pending')
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    employee = db.relationship('Employee', backref='leaves')

class Payroll(db.Model):
    __tablename__ = 'payroll'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    pay_period_start = db.Column(db.Date, nullable=False)
    pay_period_end = db.Column(db.Date, nullable=False)
    basic_salary = db.Column(db.Numeric(15, 2), nullable=False)
    allowances = db.Column(db.Numeric(15, 2), default=0)
    deductions = db.Column(db.Numeric(15, 2), default=0)
    tax = db.Column(db.Numeric(15, 2), default=0)
    net_salary = db.Column(db.Numeric(15, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_date = db.Column(db.Date)
    
    employee = db.relationship('Employee', backref='payrolls')

# Helper Functions
def is_logged_in():
    return 'loggedin' in session

def is_admin():
    return session.get('is_admin', False)

def get_employee_id():
    return session.get('id')

def create_admin_user():
    """Create initial admin user if not exists"""
    admin_email = 'admin@hr.com'
    admin_password = 'Admin@1234'  # In production, use environment variables
    
    admin = Employee.query.filter_by(email=admin_email).first()
    
    if not admin:
        try:
            # Create hashed password
            hashed_password = generate_password_hash(admin_password)
            
            # Create admin employee
            admin = Employee(
                first_name='System',
                last_name='Admin',
                email=admin_email,
                password=hashed_password,
                hire_date=date.today(),
                is_admin=True,
                status='active'
            )
            db.session.add(admin)
            
            # Create default HR department
            hr_dept = Department(
                name='Human Resources',
                location='Headquarters',
                budget=100000.00
            )
            db.session.add(hr_dept)
            db.session.flush()  # To get the department ID
            
            # Create HR Manager position
            admin_position = Position(
                title='HR Manager',
                department_id=hr_dept.id,
                min_salary=50000.00,
                max_salary=100000.00
            )

            db.session.add(admin_position)
            db.session.flush()  # To get the position ID

            staff_position = Position(
                title='HR Staff',
                department_id=hr_dept.id,
                min_salary=30000.00,
                max_salary=50000.00
            )
            db.session.add(staff_position)
            
            # Assign department and position to admin
            admin.department_id = hr_dept.id
            admin.position_id = admin_position.id
            hr_dept.manager_id = admin.id  # Admin is manager of HR department
            
            db.session.commit()
            print("Default admin user created successfully!")
            print(f"Email: {admin_email}")
            print(f"Password: {admin_password}")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {str(e)}")
    else:
        print("Admin user already exists")

def generate_random_password(length=12):
    """Generate a secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        # Ensure password meets complexity requirements
        if (any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in "!@#$%^&*" for c in password)):
            return password

# def generate_password_csv(password_data):
#     """Generate CSV file with password information"""
#     si = StringIO()
#     writer = csv.writer(si)
    
#     # Write header
#     writer.writerow(['Name', 'Email', 'Password'])
    
#     # Write data
#     for user in password_data:
#         writer.writerow([user['name'], user['email'], user['password']])
    
#     output = make_response(si.getvalue())
#     output.headers['Content-Type'] = 'text/csv'
#     output.headers['Content-Disposition'] = 'attachment; filename=user_passwords.csv'
#     return output

@app.context_processor
def inject_now():
    return {
        'now': datetime.utcnow(),
        'current_year': datetime.utcnow().year
    }

# Routes
@app.route('/')
def home():
    current_year = datetime.now().year
    if not is_logged_in():
        return redirect(url_for('login'))
    
    if is_admin():
        # Admin dashboard
        emp_count = Employee.query.count()
        dept_count = Department.query.count()
        active_leaves = Leave.query.filter(Leave.status == 'approved', Leave.end_date >= date.today()).count()
        
        recent_hires = Employee.query.order_by(Employee.hire_date.desc()).limit(5).all()
        
        return render_template('admin/dashboard.html', 
                            emp_count=emp_count, 
                            dept_count=dept_count,
                            active_leaves=active_leaves,
                            recent_hires=recent_hires,
                            current_year=current_year)
    else:
        # Employee dashboard
        employee = Employee.query.get(get_employee_id())
        
        current_month = date.today().month
        current_year = date.today().year
        attendance = Attendance.query.filter(
            Attendance.employee_id == get_employee_id(),
            db.extract('month', Attendance.date) == current_month,
            db.extract('year', Attendance.date) == current_year
        ).order_by(Attendance.date.desc()).all()
        
        return render_template('employee/dashboard.html', 
                            employee=employee, 
                            attendance=attendance)
    

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_type = request.form.get('user_type', 'employee')  # Default to employee
        
        employee = Employee.query.filter_by(email=email).first()
        
        if employee and check_password_hash(employee.password, password):
            # Check if user type matches their role
            if (user_type == 'admin' and not employee.is_admin) or \
               (user_type == 'employee' and employee.is_admin):
                flash('Please use the correct login for your account type', 'warning')
                return redirect(url_for('login'))
            
            # Set session variables
            session['loggedin'] = True
            session['id'] = employee.id
            session['email'] = employee.email
            session['is_admin'] = employee.is_admin
            
            # Redirect based on user type
            if employee.is_admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Incorrect email/password!', 'danger')
    
    return render_template('login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        employee = Employee.query.filter_by(email=email, is_admin=True).first()
        
        if employee and check_password_hash(employee.password, password):
            # Set session variables
            session['loggedin'] = True
            session['id'] = employee.id
            session['email'] = employee.email
            session['first_name'] = employee.first_name
            session['last_name'] = employee.last_name
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'danger')
    
    # Pass login_type to template
    return render_template('login.html', login_type='admin')

@app.route('/employee/login', methods=['GET', 'POST'])
def employee_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        employee = Employee.query.filter_by(email=email, is_admin=False).first()
        
        if employee and check_password_hash(employee.password, password):
            # Set session variables
            session['loggedin'] = True
            session['id'] = employee.id
            session['email'] = employee.email
            session['first_name'] = employee.first_name
            session['last_name'] = employee.last_name
            session['is_admin'] = False
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid employee credentials', 'danger')
    
    # Pass login_type to template
    return render_template('login.html', login_type='employee')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Admin dashboard logic
    emp_count = Employee.query.count()
    dept_count = Department.query.count()
    active_leaves = Leave.query.filter(Leave.status == 'approved', Leave.end_date >= date.today()).count()
    
    recent_hires = Employee.query.order_by(Employee.hire_date.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', 
                        emp_count=emp_count, 
                        dept_count=dept_count,
                        active_leaves=active_leaves,
                        recent_hires=recent_hires)

@app.route('/employee/dashboard')
def employee_dashboard():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    employee = Employee.query.get(get_employee_id())
    
    current_month = date.today().month
    current_year = date.today().year
    attendance = Attendance.query.filter(
        Attendance.employee_id == get_employee_id(),
        db.extract('month', Attendance.date) == current_month,
        db.extract('year', Attendance.date) == current_year
    ).order_by(Attendance.date.desc()).all()
    
    return render_template('employee/dashboard.html', 
                        employee=employee, 
                        attendance=attendance)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Employee Management Routes
@app.route('/employees')
def employees():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Get filter parameters
    department_id = request.args.get('department_id', type=int)
    status = request.args.get('status')
    position_id = request.args.get('position_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    
    # Build query
    query = Employee.query
    
    if department_id:
        query = query.filter_by(department_id=department_id)
    if status:
        query = query.filter_by(status=status)
    if position_id:
        query = query.filter_by(position_id=position_id)
    
    # Paginate the results
    pagination = query.order_by(Employee.last_name.asc()).paginate(page=page, per_page=per_page)
    
    return render_template('admin/employees/list.html',
                        employees=pagination.items,
                        pagination=pagination,
                        all_departments=Department.query.all(),
                        all_positions=Position.query.all())

@app.route('/employee/add', methods=['GET', 'POST'])
def add_employee():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Create new employee
            employee = Employee(
                first_name=request.form['first_name'],
                last_name=request.form['last_name'],
                email=request.form['email'],
                phone=request.form.get('phone'),
                hire_date=datetime.strptime(request.form['hire_date'], '%Y-%m-%d').date(),
                position_id=request.form['position_id'],
                salary=float(request.form['salary']),
                manager_id=request.form.get('manager_id') or None,
                department_id=request.form.get('department_id') or None,
                status=request.form['status'],
                password=generate_password_hash('defaultpassword'),  # Set default password
                is_admin='is_admin' in request.form,
                created_at=datetime.utcnow()
            )
            
            db.session.add(employee)
            db.session.commit()
            
            flash('Employee added successfully!', 'success')
            return redirect(url_for('employees'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding employee: {str(e)}', 'danger')
    
    # For GET requests
    return render_template('admin/employees/add.html',
                         positions=Position.query.all(),
                         managers=Employee.query.all(),
                         departments=Department.query.all())

@app.route('/employee/edit/<int:id>', methods=['GET', 'POST'])
def edit_employee(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    employee = Employee.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            employee.first_name = request.form['first_name']
            employee.last_name = request.form['last_name']
            employee.email = request.form['email']
            employee.phone = request.form.get('phone')
            employee.position_id = request.form['position_id']
            employee.salary = float(request.form['salary'])
            employee.manager_id = request.form.get('manager_id') or None
            employee.department_id = request.form.get('department_id') or None
            employee.status = request.form['status']
            employee.is_admin = 'is_admin' in request.form
            
            db.session.commit()
            flash('Employee updated successfully!', 'success')
            return redirect(url_for('employees'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating employee: {str(e)}', 'danger')
    
    positions = Position.query.all()
    managers = Employee.query.filter(Employee.id != id).all()
    departments = Department.query.all()
    
    return render_template('admin/employees/edit.html',
                         employee=employee,
                         positions=positions,
                         managers=managers,
                         departments=departments)

@app.route('/employee/delete/<int:id>')
def delete_employee(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    employee = Employee.query.get_or_404(id)
    try:
        employee.status = 'terminated'
        db.session.commit()
        flash('Employee terminated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error terminating employee: {str(e)}', 'danger')
    
    return redirect(url_for('employees'))

@app.route('/employee/leaves')
def employee_leaves():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    leaves = Leave.query.filter_by(employee_id=get_employee_id()).order_by(Leave.start_date.desc()).all()
    return render_template('employee/leaves/list.html', leaves=leaves)

@app.route('/employee/leaves/request', methods=['GET', 'POST'])
def employee_request_leave():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            leave = Leave(
                employee_id=get_employee_id(),
                type=request.form['type'],
                start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
                reason=request.form['reason'],
                status='pending'
            )
            db.session.add(leave)
            db.session.commit()
            flash('Leave request submitted successfully!', 'success')
            return redirect(url_for('employee_leaves'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting leave request: {str(e)}', 'danger')
    
    return render_template('employee/leaves/request.html')



# @app.route('/employee/leaves/request', methods=['GET', 'POST'])
# def request_leave():
#     if not is_logged_in():
#         return redirect(url_for('login'))
    
#     if request.method == 'POST':
#         try:
#             leave = Leave(
#                 employee_id=get_employee_id(),
#                 type=request.form['type'],
#                 start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
#                 end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date(),
#                 reason=request.form['reason'],
#                 status='pending'
#             )
#             db.session.add(leave)
#             db.session.commit()
#             flash('Leave request submitted successfully!', 'success')
#             return redirect(url_for('leaves'))
#         except Exception as e:
#             db.session.rollback()
#             flash(f'Error submitting leave request: {str(e)}', 'danger')
    
#     return render_template('employee/leaves/request.html')

@app.route('/employee/profile')
def employee_profile():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    employee = Employee.query.get(get_employee_id())
    return render_template('employee/profile.html', employee=employee)

@app.route('/employee/change-password', methods=['POST'])
def employee_change_password():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    employee = Employee.query.get(get_employee_id())
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if not check_password_hash(employee.password, current_password):
        flash('Current password is incorrect', 'danger')
    elif new_password != confirm_password:
        flash('New passwords do not match', 'danger')
    else:
        try:
            employee.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
    
    return redirect(url_for('employee_profile'))

@app.route('/employee/profile/update', methods=['POST'])
def update_profile():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    employee = Employee.query.get(get_employee_id())
    try:
        employee.first_name = request.form['first_name']
        employee.last_name = request.form['last_name']
        employee.email = request.form['email']
        employee.phone = request.form.get('phone')
        # Add address field if your model has it
        db.session.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
    
    return redirect(url_for('profile'))

@app.route('/employee/password/update', methods=['POST'])
def update_password():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    employee = Employee.query.get(get_employee_id())
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if not check_password_hash(employee.password, current_password):
        flash('Current password is incorrect', 'danger')
    elif new_password != confirm_password:
        flash('New passwords do not match', 'danger')
    else:
        try:
            employee.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating password: {str(e)}', 'danger')
    
    return redirect(url_for('profile'))

# Employee Routes
from datetime import datetime  # Make sure this import is at the top of your routes file

@app.route('/employee/attendance')
def employee_attendance():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    employee_id = get_employee_id()
    attendances = Attendance.query.filter_by(employee_id=employee_id)\
                                 .order_by(Attendance.date.desc())\
                                 .all()
    
    return render_template('employee/attendance/list.html', attendances=attendances)

@app.route('/employee/attendance/mobile', methods=['GET'])
def mobile_time_tracking():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    return render_template('employee/attendance/mobile_tracking.html')

@app.route('/api/attendance/checkin', methods=['POST'])
def mobile_check_in():
    if not is_logged_in() or is_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    try:
        attendance = Attendance(
            employee_id=get_employee_id(),
            date=date.today(),
            check_in=datetime.now().time(),
            check_in_location=f"{data['lat']},{data['lng']}",
            device_info=request.user_agent.string,
            ip_address=request.remote_addr,
            is_remote=data.get('is_remote', False),
            status='pending'
        )
        db.session.add(attendance)
        db.session.commit()
        return jsonify({'success': True, 'check_in_time': attendance.check_in.strftime('%H:%M')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/attendance/checkout', methods=['POST'])
def mobile_check_out():
    if not is_logged_in() or is_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    try:
        attendance = Attendance.query.filter_by(
            employee_id=get_employee_id(),
            date=date.today()
        ).order_by(Attendance.check_in.desc()).first()
        
        if not attendance:
            return jsonify({'error': 'No check-in found for today'}), 400
            
        attendance.check_out = datetime.now().time()
        attendance.check_out_location = f"{data['lat']},{data['lng']}"
        db.session.commit()
        return jsonify({'success': True, 'check_out_time': attendance.check_out.strftime('%H:%M')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/attendance/today')
def today_attendance_status():
    if not is_logged_in() or is_admin():
        return jsonify({'error': 'Unauthorized'}), 401
    
    attendance = Attendance.query.filter_by(
        employee_id=get_employee_id(),
        date=date.today()
    ).first()
    
    if attendance:
        return jsonify({
            'check_in': True,
            'check_in_time': attendance.check_in.strftime('%H:%M'),
            'check_out_time': attendance.check_out.strftime('%H:%M') if attendance.check_out else None
        })
    return jsonify({'check_in': False})

@app.route('/admin/users/passwords', methods=['GET', 'POST'])
def manage_user_passwords():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            action = request.form.get('action')
            user_id = request.form.get('user_id')
            
            if action == 'generate_single':
                # Generate password for a single user
                employee = Employee.query.get_or_404(user_id)
                new_password = generate_random_password()
                employee.password = generate_password_hash(new_password)
                db.session.commit()
                
                flash(f"Password reset for {employee.first_name} {employee.last_name}. New password: {new_password}", 'success')
            
            elif action == 'generate_all':
                # Generate passwords for all users
                employees = Employee.query.all()
                password_updates = []
                
                for employee in employees:
                    new_password = generate_random_password()
                    employee.password = generate_password_hash(new_password)
                    password_updates.append({
                        'name': f"{employee.first_name} {employee.last_name}",
                        'email': employee.email,
                        'password': new_password
                    })
                
                db.session.commit()
                
                # For security, we'll only show the first 3 passwords in the flash message
                sample_updates = password_updates[:3]
                flash_message = "Passwords reset for all users. Sample passwords:<br>"
                flash_message += "<br>".join(
                    f"{user['name']} ({user['email']}): {user['password']}" 
                    for user in sample_updates
                )
                if len(password_updates) > 3:
                    flash_message += f"<br><br>... and {len(password_updates) - 3} more users"
                
                flash(Markup(flash_message), 'success')
                
            return redirect(url_for('manage_user_passwords'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error resetting passwords: {str(e)}', 'danger')
    
    # Get all users ordered by admin status then name
    employees = Employee.query.order_by(
        Employee.is_admin.desc(),
        Employee.first_name.asc()
    ).all()
    
    return render_template('admin/users/passwords.html', employees=employees)

@app.route('/admin/leaves')
def admin_leaves():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Get filter parameters
    status = request.args.get('status', 'pending')
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = Leave.query.join(Employee).order_by(Leave.start_date.desc())
    
    if status != 'all':
        query = query.filter(Leave.status == status)
    
    # Paginate results
    per_page = 10
    pagination = query.paginate(page=page, per_page=per_page)
    
    return render_template('admin/leaves/list.html',
                        leaves=pagination.items,
                        pagination=pagination,
                        status=status)

@app.route('/admin/leaves/process/<int:id>', methods=['POST'])
def admin_process_leave(id):  # Changed function name
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    leave = Leave.query.get_or_404(id)
    
    try:
        leave.status = request.form['status']
        leave.processed_by = get_employee_id()
        leave.processed_at = datetime.utcnow()
        db.session.commit()
        
        flash(f'Leave request has been {leave.status}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing leave request: {str(e)}', 'danger')
    
    return redirect(url_for('admin_leaves'))

@app.route('/admin/leaves/<int:id>')
def view_leave(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    leave = Leave.query.get_or_404(id)
    return render_template('admin/leaves/view.html', leave=leave)

# Department Management Routes
@app.route('/departments')
def departments():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    departments = Department.query.all()
    return render_template('admin/departments/list.html', departments=departments)

@app.route('/department/add', methods=['GET', 'POST'])
def add_department():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    managers = Employee.query.all()
    
    if request.method == 'POST':
        try:
            department = Department(
                name=request.form['name'],
                manager_id=request.form['manager_id'] or None,
                location=request.form['location'],
                budget=float(request.form['budget']) if request.form['budget'] else None
            )
            db.session.add(department)
            db.session.commit()
            flash('Department added successfully!', 'success')
            return redirect(url_for('departments'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding department: {str(e)}', 'danger')
    
    return render_template('admin/departments/add.html', managers=managers)

@app.route('/department/edit/<int:id>', methods=['GET', 'POST'])
def edit_department(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    department = Department.query.get_or_404(id)
    managers = Employee.query.all()
    
    if request.method == 'POST':
        try:
            department.name = request.form['name']
            department.manager_id = request.form['manager_id'] or None
            department.location = request.form['location']
            department.budget = float(request.form['budget']) if request.form['budget'] else None
            
            db.session.commit()
            flash('Department updated successfully!', 'success')
            return redirect(url_for('departments'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating department: {str(e)}', 'danger')
    
    return render_template('admin/departments/edit.html', department=department, managers=managers)

@app.route('/department/delete/<int:id>')
def delete_department(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    department = Department.query.get_or_404(id)
    
    try:
        # First, unassign all employees from this department
        Employee.query.filter_by(department_id=id).update({'department_id': None})
        
        # Then delete the department
        db.session.delete(department)
        db.session.commit()
        flash('Department deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting department: {str(e)}', 'danger')
    
    return redirect(url_for('departments'))

# Position Management Routes
@app.route('/positions')
def positions():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    positions = Position.query.all()
    return render_template('admin/positions/list.html', positions=positions)

@app.route('/position/add', methods=['GET', 'POST'])
def add_position():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            position = Position(
                title=request.form['title'],
                department_id=request.form['department_id'] or None,
                min_salary=float(request.form['min_salary']),
                max_salary=float(request.form['max_salary'])
            )
            db.session.add(position)
            db.session.commit()
            flash('Position added successfully!', 'success')
            return redirect(url_for('positions'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding position: {str(e)}', 'danger')
    
    departments = Department.query.all()
    return render_template('admin/positions/add.html', departments=departments)

@app.route('/position/edit/<int:id>', methods=['GET', 'POST'])
def edit_position(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    position = Position.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            position.title = request.form['title']
            position.department_id = request.form['department_id'] or None
            position.min_salary = float(request.form['min_salary'])
            position.max_salary = float(request.form['max_salary'])
            
            db.session.commit()
            flash('Position updated successfully!', 'success')
            return redirect(url_for('positions'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating position: {str(e)}', 'danger')
    
    departments = Department.query.all()
    return render_template('admin/positions/edit.html', position=position, departments=departments)

# Attendance Management Routes
@app.route('/attendance')
def attendance():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    # Get filter parameters
    employee_id = request.args.get('employee_id', type=int)
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    status = request.args.get('status')
    page = request.args.get('page', 1, type=int)
    
    # Build query
    query = Attendance.query

    if is_admin():
        # Explicitly specify the join condition
        query = query.join(Employee, Attendance.employee_id == Employee.id)
    else:
        query = query.filter_by(employee_id=get_employee_id())
    
    if employee_id:
        query = query.filter_by(employee_id=employee_id)
    if month:
        query = query.filter(db.extract('month', Attendance.date) == month)
    if year:
        query = query.filter(db.extract('year', Attendance.date) == year)
    if status:
        query = query.filter_by(status=status)
    
    # Paginate results
    per_page = 10
    pagination = query.order_by(Attendance.date.desc()).paginate(page=page, per_page=per_page)
    
    if is_admin():
        all_employees = Employee.query.order_by(Employee.first_name).all()
        return render_template('admin/attendance/list.html', 
                            attendance_records=pagination.items,
                            pagination=pagination,
                            all_employees=all_employees,
                            datetime=datetime)
    else:
        return render_template('employee/attendance.html', 
                            attendance_records=pagination.items,
                            pagination=pagination)

@app.route('/attendance/add', methods=['POST'])
def add_attendance():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    try:
        attendance = Attendance(
            employee_id=request.form['employee_id'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            check_in=datetime.strptime(request.form['check_in'], '%H:%M').time() if request.form['check_in'] else None,
            check_out=datetime.strptime(request.form['check_out'], '%H:%M').time() if request.form['check_out'] else None,
            status=request.form['status'],
            notes=request.form.get('notes')
        )
        db.session.add(attendance)
        db.session.commit()
        flash('Attendance record added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding attendance record: {str(e)}', 'danger')
    
    return redirect(url_for('attendance'))

@app.route('/attendance/edit/<int:id>', methods=['POST'])
def edit_attendance(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    attendance = Attendance.query.get_or_404(id)
    
    try:
        attendance.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        attendance.check_in = datetime.strptime(request.form['check_in'], '%H:%M').time() if request.form['check_in'] else None
        attendance.check_out = datetime.strptime(request.form['check_out'], '%H:%M').time() if request.form['check_out'] else None
        attendance.status = request.form['status']
        attendance.notes = request.form.get('notes')
        
        db.session.commit()
        flash('Attendance record updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating attendance record: {str(e)}', 'danger')
    
    return redirect(url_for('attendance'))

@app.route('/attendance/delete/<int:id>')
def delete_attendance(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    attendance = Attendance.query.get_or_404(id)
    
    try:
        db.session.delete(attendance)
        db.session.commit()
        flash('Attendance record deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting attendance record: {str(e)}', 'danger')
    
    return redirect(url_for('attendance'))

# Leave Management Routes
@app.route('/leaves')
def leaves():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    if is_admin():
        leaves = Leave.query.order_by(Leave.start_date.desc()).all()
        return render_template('admin/leaves/list.html', leaves=leaves)
    else:
        leaves = Leave.query.filter_by(employee_id=get_employee_id()).all()
        return render_template('employee/leaves/list.html', leaves=leaves)
    
@app.route('/leave/<int:id>')
def leave_details(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    leave = Leave.query.get_or_404(id)
    return render_template('admin/leaves/details.html', leave=leave)

@app.route('/leave/process/<int:id>', methods=['POST'])
def process_leave(id):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    leave = Leave.query.get_or_404(id)
    
    try:
        leave.status = request.form['status']
        # You might want to add a manager_comment field to your Leave model
        # leave.manager_comment = request.form.get('manager_comment')
        db.session.commit()
        flash(f'Leave request has been {leave.status}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing leave request: {str(e)}', 'danger')
    
    return redirect(url_for('leave_details', id=id))

# Payroll Management Routes
@app.route('/payroll')
def payroll():  # Changed from payroll_list to payroll
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    payrolls = Payroll.query.order_by(Payroll.pay_period_start.desc()).all()
    return render_template('admin/payroll/list.html', payrolls=payrolls)

@app.route('/payroll/generate', methods=['GET', 'POST'])
def generate_payroll():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Get form data
            pay_period_start = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            pay_period_end = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            payment_date = datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date()
            include_bonus = 'include_bonus' in request.form
            
            # Get all active employees
            employees = Employee.query.filter_by(status='active').all()
            
            for employee in employees:
                # Calculate payroll - implement your business logic here
                basic_salary = employee.salary
                allowances = 0
                deductions = 0
                tax = basic_salary * 0.2  # Simplified tax calculation
                
                if include_bonus:
                    allowances += basic_salary * 0.1  # Example 10% bonus
                
                net_salary = basic_salary + allowances - deductions - tax
                
                payroll = Payroll(
                    employee_id=employee.id,
                    pay_period_start=pay_period_start,
                    pay_period_end=pay_period_end,
                    basic_salary=basic_salary,
                    allowances=allowances,
                    deductions=deductions,
                    tax=tax,
                    net_salary=net_salary,
                    payment_date=payment_date,
                    status='pending'
                )
                db.session.add(payroll)
            
            db.session.commit()
            flash('Payroll generated successfully!', 'success')
            return redirect(url_for('payroll'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error generating payroll: {str(e)}', 'danger')
    
    # Get pending payrolls for display
    pending_payrolls = Payroll.query.filter_by(status='pending').order_by(Payroll.pay_period_start.desc()).all()
    
    return render_template('admin/payroll/generate.html', pending_payrolls=pending_payrolls)

# Report Routes
@app.route('/reports/attendance')
def attendance_report():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Get filter parameters
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int, default=datetime.now().year)
    department_id = request.args.get('department', type=int)
    
    # Build base query
    query = db.session.query(
        Employee,
        Department
    ).outerjoin(
        Department, Employee.department_id == Department.id
    )
    
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    
    employees = query.all()
    
    # Calculate attendance summary for each employee
    attendance_summary = []
    for emp, dept in employees:
        attendance_query = Attendance.query.filter(
            Attendance.employee_id == emp.id
        )
        
        if month:
            attendance_query = attendance_query.filter(
                db.extract('month', Attendance.date) == month
            )
        if year:
            attendance_query = attendance_query.filter(
                db.extract('year', Attendance.date) == year
            )
        
        records = attendance_query.all()
        
        counts = {
            'present': 0,
            'absent': 0,
            'late': 0,
            'early_leave': 0
        }
        
        for record in records:
            if record.status == 'present':
                counts['present'] += 1
            elif record.status == 'absent':
                counts['absent'] += 1
            elif record.status == 'late':
                counts['late'] += 1
            elif record.status == 'early_leave':
                counts['early_leave'] += 1
        
        total_days = counts['present'] + counts['absent'] + counts['late'] + counts['early_leave']
        percentage = (counts['present'] / total_days * 100) if total_days > 0 else 0
        
        attendance_summary.append({
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'department': dept,
            'attendance_counts': {
                **counts,
                'percentage': round(percentage, 1)
            }
        })
    
    departments = Department.query.all()
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    return render_template('admin/reports/attendance.html',
                         attendance_summary=attendance_summary,
                         departments=departments,
                         current_month=current_month,
                         current_year=current_year)

@app.route('/reports/employees')
def employee_report():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Overall stats
    total = Employee.query.count()
    active = Employee.query.filter_by(status='active').count()
    on_leave = db.session.query(Leave).filter(
        Leave.status == 'approved',
        Leave.start_date <= date.today(),
        Leave.end_date >= date.today()
    ).count()
    terminated = Employee.query.filter_by(status='terminated').count()
    
    # Department stats
    department_stats = []
    for dept in Department.query.all():
        dept_total = Employee.query.filter_by(department_id=dept.id).count()
        dept_active = Employee.query.filter_by(department_id=dept.id, status='active').count()
        dept_terminated = Employee.query.filter_by(department_id=dept.id, status='terminated').count()
        
        department_stats.append({
            'name': dept.name,
            'total': dept_total,
            'active': dept_active,
            'on_leave': 0,  # Would need to query leaves per department
            'terminated': dept_terminated,
            'active_percentage': round((dept_active / dept_total * 100), 1) if dept_total > 0 else 0
        })
    
    # Hiring trend (last 12 months)
    hiring_trend = []
    for i in range(11, -1, -1):
        month_date = date.today() - timedelta(days=30*i)  # Now using timedelta
        month_name = month_date.strftime('%b %Y')
        count = Employee.query.filter(
            db.extract('year', Employee.hire_date) == month_date.year,
            db.extract('month', Employee.hire_date) == month_date.month
        ).count()
        
        hiring_trend.append({
            'month': month_name,
            'count': count
        })
    
    return render_template('admin/reports/employees.html',
                         employee_stats={
                             'total': total,
                             'active': active,
                             'on_leave': on_leave,
                             'terminated': terminated
                         },
                         department_stats=department_stats,
                         hiring_trend=hiring_trend)

@app.route('/reports/employees/export/<format>')
def generate_employee_report(format):
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Get the report data
    employee_stats = {
        'total': Employee.query.count(),
        'active': Employee.query.filter_by(status='active').count(),
        'on_leave': db.session.query(Leave).filter(
            Leave.status == 'approved',
            Leave.start_date <= date.today(),
            Leave.end_date >= date.today()
        ).count(),
        'terminated': Employee.query.filter_by(status='terminated').count()
    }
    
    department_stats = []
    for dept in Department.query.all():
        dept_total = Employee.query.filter_by(department_id=dept.id).count()
        dept_active = Employee.query.filter_by(department_id=dept.id, status='active').count()
        department_stats.append({
            'name': dept.name,
            'total': dept_total,
            'active': dept_active,
            'active_percentage': round((dept_active / dept_total * 100), 1) if dept_total > 0 else 0
        })
    
    if format == 'excel':
        return generateE_excel_report(employee_stats, department_stats)
    # Add other formats (pdf, csv) as needed
    else:
        flash('Invalid export format', 'error')
        return redirect(url_for('employee_report'))

@app.route('/generate_attendance_report', methods=['POST'])
def generate_attendance_report():
    if not is_logged_in() or not is_admin():
        return redirect(url_for('login'))
    
    # Get filters from form
    employee_id = request.form.get('employee_id')
    month = request.form.get('month')
    year = request.form.get('year')
    status = request.form.get('status')
    
    # Build query
    query = Attendance.query.join(Employee)
    
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    if month:
        query = query.filter(db.extract('month', Attendance.date) == month)
    if year:
        query = query.filter(db.extract('year', Attendance.date) == year)
    if status:
        query = query.filter(Attendance.status == status)
    
    records = query.order_by(Attendance.date.desc()).all()
    
    # Get report parameters
    report_type = request.form['report_type']
    report_title = request.form['report_title']
    group_by = request.form.get('group_by')
    include_summary = 'include_summary' in request.form
    
    if report_type == 'pdf':
        return generate_pdf_report(records, report_title, group_by, include_summary)
    elif report_type == 'excel':
        return generateA_excel_report(records, report_title, group_by, include_summary)
    elif report_type == 'csv':
        return generate_csv_report(records, report_title, group_by, include_summary)
    else:
        flash('Invalid report type', 'danger')
        return redirect(url_for('attendance'))
    
@app.route('/employee/attendance/submit', methods=['GET', 'POST'])
def submit_attendance():
    if not is_logged_in() or is_admin():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            # Validate form data
            attendance_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            if attendance_date > date.today():
                flash("Cannot submit attendance for future dates", 'danger')
                return redirect(url_for('submit_attendance'))
            
            check_in = datetime.strptime(request.form['check_in'], '%H:%M').time()
            check_out = datetime.strptime(request.form['check_out'], '%H:%M').time() if request.form['check_out'] else None
            
            if check_out and check_out <= check_in:
                flash("Check out time must be after check in time", 'danger')
                return redirect(url_for('submit_attendance'))
            
            # Create attendance record
            attendance = Attendance(
                employee_id=get_employee_id(),
                date=attendance_date,
                check_in=check_in,
                check_out=check_out,
                status='pending',
                notes=request.form.get('notes', ''),
                submitted_at=datetime.utcnow()
            )
            
            db.session.add(attendance)
            db.session.commit()
            
            flash('Attendance submitted successfully! Waiting for manager approval.', 'success')
            return redirect(url_for('employee_attendance'))
            
        except ValueError as e:
            db.session.rollback()
            flash('Invalid time format. Please use HH:MM format.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error submitting attendance: {str(e)}', 'danger')
    
    # For GET requests or failed POST requests
    return render_template('employee/attendance/submit.html', now=datetime.now())

# Manager views pending approvals
@app.route('/manager/attendance/approvals')
def attendance_approvals():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    # Get current employee and check if they're a manager
    manager = Employee.query.get(get_employee_id())
    if not manager or not manager.subordinates:
        flash('You are not authorized to approve attendances', 'danger')
        return redirect(url_for('home'))
    
    # Get pending attendances from subordinates
    subordinate_ids = [emp.id for emp in manager.subordinates]
    pending_attendances = Attendance.query.filter(
        Attendance.employee_id.in_(subordinate_ids),
        Attendance.status == 'pending'
    ).order_by(Attendance.date.desc()).all()
    
    return render_template('manager/attendance/approvals.html', 
                         pending_attendances=pending_attendances)

# Manager approves/rejects attendance
@app.route('/manager/attendance/process/<int:id>', methods=['POST'])
def process_attendance(id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    attendance = Attendance.query.get_or_404(id)
    manager = Employee.query.get(get_employee_id())
    
    # Verify the manager has authority to approve this attendance
    if attendance.employee.manager_id != manager.id:
        flash('You are not authorized to approve this attendance', 'danger')
        return redirect(url_for('attendance_approvals'))
    
    try:
        attendance.status = request.form['status']  # 'approved' or 'rejected'
        attendance.approved_by = manager.id
        attendance.approved_at = datetime.utcnow()
        db.session.commit()
        
        status = attendance.status
        flash(f'Attendance {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing attendance: {str(e)}', 'danger')
    
    return redirect(url_for('attendance_approvals'))
    
def generate_pdf_report(data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    # Add title
    elements.append(Paragraph("Employee Report", styles['Title']))
    
    # Add employee stats
    elements.append(Paragraph("Summary Statistics", styles['Heading2']))
    stats_data = [
        ["Metric", "Count"],
        ["Total Employees", str(data['employee_stats']['total'])],
        ["Active Employees", str(data['employee_stats']['active'])],
        ["Employees on Leave", str(data['employee_stats']['on_leave'])],
        ["Terminated Employees", str(data['employee_stats']['terminated'])]
    ]
    
    stats_table = Table(stats_data)
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(stats_table)
    
    # Add space between sections
    elements.append(Spacer(1, 20))
    
    # Add department stats
    elements.append(Paragraph("Department Statistics", styles['Heading2']))
    dept_data = [["Department", "Total", "Active", "Terminated", "% Active"]]
    for dept in data['department_stats']:
        dept_data.append([
            dept['name'],
            str(dept['total']),
            str(dept['active']),
            str(dept['terminated']),
            f"{dept['active_percentage']}%"
        ])
    
    dept_table = Table(dept_data)
    dept_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(dept_table)
    
    # Build the PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=employee_report.pdf'
    return response

def generateE_excel_report(employee_stats, department_stats):
    from io import BytesIO
    from xlsxwriter import Workbook
    
    output = BytesIO()
    workbook = Workbook(output)
    worksheet = workbook.add_worksheet('Employee Report')
    
    # Formats
    bold = workbook.add_format({'bold': True})
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#D3D3D3',
        'border': 1
    })
    percent_format = workbook.add_format({'num_format': '0.00%'})
    
    # Title
    worksheet.write(0, 0, 'Employee Report', bold)
    
    # Employee statistics
    worksheet.write(2, 0, 'Employee Statistics', bold)
    worksheet.write_row(3, 0, ['Metric', 'Count'], header_format)
    
    stats_data = [
        ('Total Employees', employee_stats['total']),
        ('Active Employees', employee_stats['active']),
        ('On Leave', employee_stats['on_leave']),
        ('Terminated', employee_stats['terminated'])
    ]
    
    for row, (metric, count) in enumerate(stats_data, start=4):
        worksheet.write(row, 0, metric)
        worksheet.write(row, 1, count)
    
    # Department statistics
    worksheet.write(8, 0, 'Department Statistics', bold)
    worksheet.write_row(9, 0, 
                       ['Department', 'Total', 'Active', '% Active'], 
                       header_format)
    
    for row, dept in enumerate(department_stats, start=10):
        worksheet.write(row, 0, dept['name'])
        worksheet.write(row, 1, dept['total'])
        worksheet.write(row, 2, dept['active'])
        worksheet.write(row, 3, dept['active_percentage'] / 100, percent_format)
    
    # Adjust column widths
    worksheet.set_column('A:A', 25)  # Department column
    worksheet.set_column('B:D', 15)  # Other columns
    
    workbook.close()
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=employee_report.xlsx'
    return response

def generate_csv_report(data):
    si = StringIO()
    writer = csv.writer(si)
    
    writer.writerow(['Employee Report'])
    writer.writerow([])
    writer.writerow(['Summary Statistics'])
    writer.writerow(['Total Employees', data['employee_stats']['total']])
    # ... add other stats
    
    writer.writerow([])
    writer.writerow(['Department Statistics'])
    writer.writerow(['Department', 'Total', 'Active', 'Terminated', '% Active'])
    for dept in data['department_stats']:
        writer.writerow([
            dept['name'],
            dept['total'],
            dept['active'],
            dept['terminated'],
            dept['active_percentage']
        ])
    
    output = make_response(si.getvalue())
    output.headers['Content-Type'] = 'text/csv'
    output.headers['Content-Disposition'] = 'attachment; filename=employee_report.csv'
    return output   

def generateA_excel_report(records, title, group_by, include_summary):
    import pandas as pd
    from io import BytesIO
    
    data = []
    for record in records:
        data.append({
            'Date': record.date.strftime('%Y-%m-%d'),
            'Employee': f"{record.employee.first_name} {record.employee.last_name}",
            'Check In': record.check_in.strftime('%H:%M') if record.check_in else None,
            'Check Out': record.check_out.strftime('%H:%M') if record.check_out else None,
            'Status': record.status.capitalize(),
            'Notes': record.notes
        })
    
    df = pd.DataFrame(data)
    
    if group_by:
        if group_by == 'employee':
            df = df.sort_values(by=['Employee', 'Date'])
        elif group_by == 'month':
            df['Month'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m')
            df = df.sort_values(by=['Month', 'Employee'])
        elif group_by == 'status':
            df = df.sort_values(by=['Status', 'Date'])
    
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Attendance', index=False)
    
    if include_summary:
        summary = df['Status'].value_counts().reset_index()
        summary.columns = ['Status', 'Count']
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    writer.close()
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename={title.replace(" ", "_")}.xlsx'
    return response

def generate_csv_report(records, title, group_by, include_summary):
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow(['Date', 'Employee', 'Check In', 'Check Out', 'Status', 'Notes'])
    
    # Write data
    for record in records:
        writer.writerow([
            record.date.strftime('%Y-%m-%d'),
            f"{record.employee.first_name} {record.employee.last_name}",
            record.check_in.strftime('%H:%M') if record.check_in else '',
            record.check_out.strftime('%H:%M') if record.check_out else '',
            record.status.capitalize(),
            record.notes or ''
        ])
    
    if include_summary:
        writer.writerow([])
        writer.writerow(['Summary Statistics'])
        writer.writerow(['Total Records', len(records)])
        
        status_counts = {}
        for record in records:
            status_counts[record.status] = status_counts.get(record.status, 0) + 1
        
        for status, count in status_counts.items():
            writer.writerow([status.capitalize(), count])
    
    output = make_response(si.getvalue())
    output.headers['Content-Type'] = 'text/csv'
    output.headers['Content-Disposition'] = f'attachment; filename={title.replace(" ", "_")}.csv'
    return output

def initialize_app():
    with app.app_context():
        try:
            db.drop_all()
            db.session.commit()  # Explicit commit for MySQL
            db.create_all()
            create_admin_user()
            
            # Create a regular employee
            regular_employee = Employee(
                first_name='John',
                last_name='Doe',
                email='employee@hr.com',
                password=generate_password_hash('Employee@1234'),  # Set default password
                hire_date=date.today(),
                is_admin=False,
                status='active'
            )
            db.session.add(regular_employee)
            
            # Assign to HR department and position if they exist
            hr_dept = Department.query.filter_by(name='Human Resources').first()
            hr_position = Position.query.filter_by(title='HR Staff').first()
            
            if hr_dept and hr_position:
                regular_employee.department_id = hr_dept.id
                regular_employee.position_id = hr_position.id
            
            db.session.commit()
            print("Initialization successful!")
            print("Admin credentials: admin@hr.com / Admin@1234")
            print("Employee credentials: employee@hr.com / Employee@1234")
            
        except Exception as e:
            print(f"Initialization failed: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    initialize_app()
    app.run(debug=True)