# from odoo import http


# class EmployeeSalary(http.Controller):
#     @http.route('/employee_salary/employee_salary', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/employee_salary/employee_salary/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('employee_salary.listing', {
#             'root': '/employee_salary/employee_salary',
#             'objects': http.request.env['employee_salary.employee_salary'].search([]),
#         })

#     @http.route('/employee_salary/employee_salary/objects/<model("employee_salary.employee_salary"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('employee_salary.object', {
#             'object': obj
#         })

