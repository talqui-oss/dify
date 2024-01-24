# -*- coding:utf-8 -*-
import json
import logging
from controllers.console import api
from controllers.console.app.error import AppNotFoundError

from extensions.ext_database import db
from flask import request, Response, stream_with_context
from flask_restful import Resource, marshal_with, reqparse
from libs.helper import uuid_value
from models.model import App
from werkzeug.exceptions import InternalServerError, NotFound

# from controllers.web import completion
from typing import Union, Generator
from services.completion_service__talqui import CompletionService
from fields.conversation_fields import message_detail_fields
from models.model import Message
from controllers.service_api.app import create_or_update_end_user_for_user_id


def _get_app(app_id, tenant_id):
    app = (
        db.session.query(App)
        .filter(App.id == app_id, App.tenant_id == tenant_id)
        .first()
    )
    if not app:
        raise AppNotFoundError
    return app


def compact_response(response: Union[dict, Generator]) -> Response:
    if isinstance(response, dict):
        return Response(
            response=json.dumps(response), status=200, mimetype="application/json"
        )
    else:

        def generate() -> Generator:
            for chunk in response:
                yield chunk

        return Response(
            stream_with_context(generate()), status=200, mimetype="text/event-stream"
        )


class TalquiChatApi(Resource):
    def post(self, app_id):
        parser = reqparse.RequestParser()
        parser.add_argument("history", type=list, required=True, location="json")
        parser.add_argument("inputs", type=dict, required=True, location="json")
        parser.add_argument("query", type=str, required=True, location="json")
        parser.add_argument("contactID", type=str, required=True, location="json")
        parser.add_argument(
            "response_mode",
            type=str,
            choices=["blocking", "streaming"],
            location="json",
        )
        parser.add_argument("conversation_id", type=uuid_value, location="json")
        parser.add_argument(
            "retriever_from",
            type=str,
            required=False,
            default="web_app",
            location="json",
        )

        args = parser.parse_args()

        streaming = args["response_mode"] == "streaming"

        """Get app detail"""
        tenant_id = request.headers.get("x-tenant-id")
        app_id = str(app_id)
        app_model = _get_app(app_id, tenant_id)

        end_user = create_or_update_end_user_for_user_id(app_model, args["contactID"])

        try:
            response = CompletionService.talqui_completion(
                app_id=str(app_id),
                app_model=app_model,
                user=end_user,
                args=args,
                from_source="service-api",
                streaming=streaming,
            )
            logging.info(response)
            return compact_response(response)
        except Exception as e:
            logging.exception("internal server error.")
            raise InternalServerError()


api.add_resource(TalquiChatApi, "/talqui/apps/<uuid:app_id>/chat-messages")


class TalquiMessageApi(Resource):
    @marshal_with(message_detail_fields)
    def get(self, app_id, message_id):
        app_id = str(app_id)
        message_id = str(message_id)

        """Get app detail"""
        tenant_id = request.headers.get("x-tenant-id")
        app_id = str(app_id)
        app_model = _get_app(app_id, tenant_id)

        message = (
            db.session.query(Message)
            .filter(Message.id == message_id, Message.app_id == app_model.id)
            .first()
        )

        if not message:
            raise NotFound("Message Not Exists.")

        return message


api.add_resource(
    TalquiMessageApi, "/talqui/apps/<uuid:app_id>/messages/<uuid:message_id>"
)
