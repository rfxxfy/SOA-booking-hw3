import logging
import os

import grpc

logger = logging.getLogger(__name__)

API_KEY_HEADER = "x-api-key"
EXPECTED_API_KEY = os.getenv("GRPC_API_KEY", "dev-api-key")


class AuthInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata or ())
        api_key = metadata.get(API_KEY_HEADER)

        if not api_key or api_key != EXPECTED_API_KEY:
            logger.warning("authentication failed for method=%s", handler_call_details.method)
            handler = continuation(handler_call_details)
            if handler is None:
                return None

            def unauthorized(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "invalid or missing API key")

            if handler.unary_unary:
                return grpc.unary_unary_rpc_method_handler(
                    unauthorized,
                    request_deserializer=handler.request_deserializer,
                    response_serializer=handler.response_serializer,
                )
            return handler

        return continuation(handler_call_details)
