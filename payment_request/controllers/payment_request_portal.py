from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
import base64
import json
from urllib.parse import urlencode


class PortalPaymentRequest(http.Controller):

    def _get_portal_context(self, error=None, form_data=None, page=1, step=20, filters=None):
        filters = filters or {}
        Request = request.env['payment.request'].sudo()
        current_partner = request.env.user.partner_id
        current_user = request.env.user
        domain = ['|', ('partner_id', '=',current_partner.id), ('requester_id', '=', current_user.id)]
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('due_date_from'):
            domain.append(('due_date', '>=', filters['due_date_from']))
        if filters.get('due_date_to'):
            domain.append(('due_date', '<=', filters['due_date_to']))
        if filters.get('description'):
            domain.append(('description', 'ilike', filters['description']))
        total = Request.search_count(domain)
        pager = portal_pager(
            url="/my/payment-request",
            total=total,
            page=page,
            step=step,
            url_args=filters,
        )
        requests = Request.search(domain, limit=step, offset=pager['offset'], order='create_date desc')
        payment_basis_options = Request._fields['payment_basis'].selection
        no_invoice_options = Request._fields['no_invoice_option'].selection
        state_options = Request._fields['state'].selection
        currencies = request.env['res.currency'].sudo().search([])
        default_currency = request.env.ref('base.USD', raise_if_not_found=False) or request.env[
            'res.currency'].sudo().search([('name', '=', 'USD')], limit=1) or request.env.company.currency_id
        projects = request.env['hr.department'].sudo().search([])
        partner = current_partner
        partners = partner

        # When re-rendering after a validation error, restore the selected partner
        form_partner = None
        if form_data and form_data.get('partner_id'):
            try:
                form_partner = request.env['res.partner'].sudo().browse(int(form_data['partner_id']))
            except Exception:
                form_partner = None

        filters_query = urlencode(filters)
        return {
            "requests": requests,
            "pager": pager,
            "payment_basis_options": payment_basis_options,
            "no_invoice_options": no_invoice_options,
            "state_options": state_options,
            "currencies": currencies,
            "default_currency": default_currency,
            "projects": projects,
            "partner": partner,
            "partners": partners,
            "error": error,
            "form_data": form_data or {},
            "form_partner": form_partner,
            "filters": filters,
            "filters_query": filters_query,
        }

    @http.route(['/my/payment-request'], type='http', auth="user", website=True)
    def portal_payment_request(self, error=None, page=1, **kw):
        filters = {}
        if kw.get('state'):
            filters['state'] = kw['state']
        if kw.get('due_date_from'):
            filters['due_date_from'] = kw['due_date_from']
        if kw.get('due_date_to'):
            filters['due_date_to'] = kw['due_date_to']
        if kw.get('description'):
            filters['description'] = kw['description']
        return request.render(
            "payment_request.portal_payment_request_list",
            self._get_portal_context(error=error, page=int(page) if page else 1, filters=filters),
        )

    @http.route(['/my/payment-request/new'], type='http', auth="user", website=True)
    def portal_payment_request_form(self, error=None, **kw):
        # form page (prefill with query params if any)
        return request.render(
            "payment_request.portal_payment_request_form",
            self._get_portal_context(error=error, form_data=kw, page=1),
        )

    @http.route(['/my/payment-request/create'], type='http', auth="user", website=True, methods=['POST'])
    def portal_create_payment_request(self, **post):
        partner_id_str = (post.get("partner_id") or "").strip()
        description = (post.get("description") or "").strip()
        long_description = (post.get("long_description") or "").strip()
        amount = post.get("amount", "").strip()
        payment_basis = post.get("payment_basis") or "invoice"
        invoice_file = request.httprequest.files.get("invoice")
        no_inv_option = post.get("no_invoice_option") or None

        if not partner_id_str:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="partner_required", form_data=post),
            )
        try:
            partner_id = int(partner_id_str)
        except Exception:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="partner_required", form_data=post),
            )

        if not description:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="description_required", form_data=post),
            )

        if not amount:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="amount_required", form_data=post),
            )

        try:
            amount = float(amount)
        except ValueError:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="amount_invalid", form_data=post),
            )

        if amount <= 0:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="amount_required", form_data=post),
            )

        if payment_basis == "invoice" and (not invoice_file or not invoice_file.filename):
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="invoice_required", form_data=post),
            )

        if payment_basis == "no_invoice" and not no_inv_option:
            return request.render(
                "payment_request.portal_payment_request_form",
                self._get_portal_context(error="no_invoice_option_required", form_data=post),
            )

        default_currency = request.env.ref('base.USD', raise_if_not_found=False) or request.env[
            'res.currency'].sudo().search([('name', '=', 'USD')], limit=1) or request.env.company.currency_id
        vals = {
            "partner_id": partner_id,
            "requester_id": request.env.user.id,
            "amount": amount,
            "description": description,
            "long_description": long_description,
            "payment_basis": payment_basis,
            "no_invoice_option": no_inv_option or "payoneer_wise",
            "currency_id": int(post.get("currency_id")) if post.get("currency_id") else default_currency.id,
            "due_date": post.get("due_date") or False,
            "project": int(post.get("project")) if post.get("project") else False,
        }

        option = vals.get("no_invoice_option")
        if option == "bank_card":
            vals.update({
                "bank_card_name": post.get("bank_card_name"),
                "bank_card_number": post.get("bank_card_number"),
                "bank_card_ussuing_bank": post.get("bank_card_ussuing_bank"),
            })
        elif option == "int_bank_account":
            vals.update({
                "int_bank_acc_name": post.get("int_bank_acc_name"),
                "int_bank_acc_iban": post.get("int_bank_acc_iban"),
                "int_bank_acc_bic": post.get("int_bank_acc_bic"),
                "int_bank_acc_bank": post.get("int_bank_acc_bank"),
                "int_bank_acc_bank_address": post.get("int_bank_acc_bank_address"),
            })
        elif option == "paypal":
            vals.update({
                "paypal_name": post.get("paypal_name"),
                "paypal_email": post.get("paypal_email"),
            })
        elif option == "payoneer_wise":
            vals.update({
                "payoneer_wise_name": post.get("payoneer_wise_name"),
                "payoneer_wise_acc_number": post.get("payoneer_wise_acc_number"),
                "payoneer_wise_aba": post.get("payoneer_wise_aba"),
            })
        elif option == "crypto":
            vals.update({
                "crypto_wallet_address": post.get("crypto_wallet_address"),
                "crypto_network": post.get("crypto_network"),
            })

        payment_request = request.env['payment.request'].sudo().create(vals)

        if invoice_file and invoice_file.filename:
            file_data = invoice_file.read()
            attachment = request.env['ir.attachment'].sudo().create({
                "name": invoice_file.filename,
                "datas": base64.b64encode(file_data).decode("ascii"),
                "res_model": "payment.request",
                "res_id": payment_request.id,
                "mimetype": invoice_file.content_type or "application/octet-stream",
                "type": "binary",
            })
            payment_request.write({"invoice": [(4, attachment.id)]})

        return request.redirect('/my/payment-request')

    @http.route(['/my/payment-request/partner-search'], type='http', auth="user", website=True,
                methods=['GET', 'POST'], csrf=False)
    def partner_search(self, term='', limit=20, **kwargs):
        raw_body = request.httprequest.get_data(as_text=True)
        try:
            data = json.loads(raw_body) if raw_body else {}
        except Exception:
            data = {}
        term = data.get('term') or kwargs.get('term') or term or request.params.get('term') or ''
        limit = int(data.get('limit') or kwargs.get('limit') or limit)

        Partner = request.env['res.partner'].sudo()
        domain = [('name', 'ilike', term)] if term else []
        partners = Partner.search(domain, limit=limit, order='name')
        payload = [{"id": p.id, "name": p.display_name} for p in partners]
        return request.make_response(json.dumps(payload), headers={'Content-Type': 'application/json'})

    @http.route(['/my/payment-request/partner-create'], type='json', auth="user", website=True, methods=['POST'],
                csrf=False)
    def partner_create(self, **kwargs):
        data = kwargs or {}
        if not data:
            raw_body = request.httprequest.get_data(as_text=True)
            try:
                data = json.loads(raw_body) if raw_body else {}
            except Exception:
                data = {}
        name = (data.get('name') or '').strip()
        email = (data.get('email') or '').strip() or False
        phone = (data.get('phone') or '').strip() or False
        if not name:
            return {'error': 'name_required'}
        partner = request.env['res.partner'].sudo().create({
            'name': name,
            'email': email,
            'phone': phone,
        })
        safe_name = partner.name or partner.display_name or ''
        return {'id': partner.id, 'name': safe_name, 'display_name': partner.display_name or safe_name}

    @http.route(['/my/payment-request/<int:request_id>/duplicate'], type='http', auth="user", website=True,
                methods=['GET'])
    def portal_duplicate_payment_request(self, request_id, **post):
        current_partner = request.env.user.partner_id
        current_user = request.env.user
        record = request.env['payment.request'].sudo().browse(request_id)
        if not record or not record.exists():
            return request.not_found()
        if record.partner_id.id != current_partner.id and record.requester_id.id != current_user.id:
            return request.not_found()

        # Prefill form with source request values (no invoice file is carried over)
        form_data = {
            "partner_id": str(record.partner_id.id or ""),
            "description": record.description or "",
            # due date and long_description intentionally not prefetched on duplicate
            "long_description": "",
            "due_date": "",
            "project": record.project and str(record.project.id) or "",
            "payment_basis": record.payment_basis or "invoice",
            "no_invoice_option": record.no_invoice_option or "payoneer_wise",
            "currency_id": record.currency_id and str(record.currency_id.id) or "",
            "amount": record.amount or "",
            "bank_card_name": record.bank_card_name or "",
            "bank_card_number": record.bank_card_number or "",
            "bank_card_ussuing_bank": record.bank_card_ussuing_bank or "",
            "int_bank_acc_name": record.int_bank_acc_name or "",
            "int_bank_acc_iban": record.int_bank_acc_iban or "",
            "int_bank_acc_bic": record.int_bank_acc_bic or "",
            "int_bank_acc_bank": record.int_bank_acc_bank or "",
            "int_bank_acc_bank_address": record.int_bank_acc_bank_address or "",
            "paypal_name": record.paypal_name or "",
            "paypal_email": record.paypal_email or "",
            "payoneer_wise_name": record.payoneer_wise_name or "",
            "payoneer_wise_acc_number": record.payoneer_wise_acc_number or "",
            "payoneer_wise_aba": record.payoneer_wise_aba or "",
            "crypto_wallet_address": record.crypto_wallet_address or "",
            "crypto_network": record.crypto_network or "",
            # invoice not copied on duplicate
        }
        return request.render(
            "payment_request.portal_payment_request_form",
            self._get_portal_context(form_data=form_data, page=1),
        )

    def _parse_filters(self, params):
        filters = {}
        if params.get('state'):
            filters['state'] = params['state']
        if params.get('due_date_from'):
            filters['due_date_from'] = params['due_date_from']
        if params.get('due_date_to'):
            filters['due_date_to'] = params['due_date_to']
        if params.get('description'):
            filters['description'] = params['description']
        return filters

    def _get_neighbor_ids(self, record, filters=None):
        current_partner = request.env.user.partner_id
        current_user = request.env.user
        domain = ['|', ('partner_id', '=', current_partner.id), ('requester_id', '=', current_user.id)]
        filters = filters or {}
        if filters.get('state'):
            domain.append(('state', '=', filters['state']))
        if filters.get('due_date_from'):
            domain.append(('due_date', '>=', filters['due_date_from']))
        if filters.get('due_date_to'):
            domain.append(('due_date', '<=', filters['due_date_to']))
        if filters.get('description'):
            domain.append(('description', 'ilike', filters['description']))
        ids = request.env['payment.request'].sudo().search(domain, order='create_date desc').ids
        prev_id = next_id = None
        if record.id in ids:
            idx = ids.index(record.id)
            if idx > 0:
                next_id = ids[idx - 1]  # newer (previous in list)
            if idx < len(ids) - 1:
                prev_id = ids[idx + 1]  # older (next in list)
        return prev_id, next_id

    @http.route(['/my/payment-request/<int:request_id>/invoice'], type='http', auth="user", website=True)
    def portal_payment_request_invoice(self, request_id, **kw):
        current_partner = request.env.user.partner_id
        current_user = request.env.user
        record = request.env['payment.request'].sudo().browse(request_id)
        if not record or not record.exists():
            return request.not_found()
        if record.partner_id.id != current_partner.id and record.requester_id.id != current_user.id:
            return request.not_found()
        if not record.invoice:
            return request.not_found()

        att = record.message_main_attachment_id
        if not att or att not in record.invoice:
            return request.not_found()

        content = att.raw
        if not content:
            return request.not_found()

        filename = att.name or f"invoice_{record.id}.pdf"
        return request.make_response(
            content,
            headers=[
                ("Content-Type", att.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'attachment; filename="{filename}"'),
            ],
        )

    @http.route(['/my/payment-request/<int:request_id>'], type='http', auth="user", website=True)
    def portal_payment_request_detail(self, request_id, **kw):
        current_partner = request.env.user.partner_id
        current_user = request.env.user
        record = request.env['payment.request'].sudo().browse(request_id)
        if not record or not record.exists():
            return request.not_found()
        if record.partner_id.id != current_partner.id and record.requester_id.id != current_user.id:
            return request.not_found()
        filters = self._parse_filters(request.params)
        prev_id, next_id = self._get_neighbor_ids(record, filters)
        filters_query = urlencode(filters)
        token = record._portal_ensure_token()
        return request.render(
            "payment_request.portal_payment_request_detail",
            {
                "request_rec": record,
                "prev_id": prev_id,
                "next_id": next_id,
                "filters_query": filters_query,
                "token": token,
            },
        )
