from flask import Flask, jsonify
from flask_login import current_user, login_required
app = Flask(__name__)

@app.route('/reports/<int:report_id>')
@login_required
def show_report(report_id):
    report = Report.query.filter_by(id=report_id, owner_id=current_user.id).first_or_404()
    return jsonify(report.to_dict())

@app.route('/reports/<int:report_id>/archive', methods=['POST'])
@login_required
def archive_report(report_id):
    report = Report.query.filter_by(id=report_id, owner_id=current_user.id).first_or_404()
    report.archived = True
    return jsonify(ok=True)
