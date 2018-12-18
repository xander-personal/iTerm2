"""Subscribe/unsubscribe from async notifications.

This module provides functions that let you subscribe and unsubscribe from notifications. iTerm2
posts notifications when some event of interest (for example, a keystroke) occurs. By subscribing to
a notifications your async callback will be run when the event occurs.
"""
import asyncio
import enum
import iterm2.api_pb2
import iterm2.connection
import iterm2.rpc
import iterm2.variables

RPC_ROLE_GENERIC = iterm2.api_pb2.RPCRegistrationRequest.Role.Value("GENERIC")
RPC_ROLE_SESSION_TITLE = iterm2.api_pb2.RPCRegistrationRequest.Role.Value("SESSION_TITLE")
RPC_ROLE_STATUS_BAR_COMPONENT = iterm2.api_pb2.RPCRegistrationRequest.Role.Value("STATUS_BAR_COMPONENT")

def _get_handlers():
    """Returns the registered notification handlers.

    :returns: (session, notification_type) -> [coroutine, ...]
    """
    if not hasattr(_get_handlers, 'handlers'):
        _get_handlers.handlers = {}
    return _get_handlers.handlers

## APIs -----------------------------------------------------------------------

class SubscriptionException(Exception):
    """Raised when a subscription attempt fails."""
    pass

async def async_unsubscribe(connection, token):
    """
    Unsubscribes from a notification.

    :param connection: A connected :class:`Connection`.
    :param token: The result of a previous subscribe call.
    """
    key, coro = token
    coros = _get_handlers()[key]
    coros.remove(coro)
    if coros:
        _get_handlers()[key] = coros
    else:
        del _get_handlers()[key]
        if len(key) == 2:
            session, notification_type = key
            await _async_subscribe(
                connection,
                False,
                notification_type,
                coro,
                session=session)
        else:
            if key[-1] == iterm2.api_pb2.NOTIFY_ON_VARIABLE_CHANGE:
                scope, identifier, name, notification_type = key
                request = iterm2.api_pb2.VariableMonitorRequest()
                request.name = name
                request.scope = scope
                request.identifier = identifier
                await _async_subscribe(
                        connection,
                        False,
                        notification_type,
                        coro,
                        key=key,
                        variable_monitor_request=request)
            else:
                # The key is custom and there should be code to handle unsubscribing as an elif clause here.
                assert False

async def async_subscribe_to_new_session_notification(connection, callback):
    """
    Registers a callback to be run when a new session is created.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an
      :class:`Connection` and iterm2.api_pb2.NewSessionNotification.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(connection, True, iterm2.api_pb2.NOTIFY_ON_NEW_SESSION, callback)

async def async_subscribe_to_keystroke_notification(connection, callback, session=None):
    """
    Registers a callback to be run when a key is pressed.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.KeystrokeNotification.
    :param session: The session to monitor, or None.

    Returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_KEYSTROKE,
        callback,
        session=session,
        keystroke_monitor_request=None)

async def async_filter_keystrokes(connection, patterns_to_ignore, session=None):
    """
    Subscribe to a pseudo-notification that causes keystrokes matching patterns to be ignored.

    :param connection: A connected :class:`Connection`.
    :param patterns_to_ignore: A list of keystroke patterns that iTerm2 should not handle, expecting the script will handle it alone. Objects are class :class:`KeystrokePattern`.
    :param session: The session to monitor, or None.

    Returns: A token that can be passed to unsubscribe.
    """
    kmr = iterm2.api_pb2.KeystrokeMonitorRequest()
    kmr.patterns_to_ignore.extend(list(map(lambda x: x.to_proto(), patterns_to_ignore)))
    async def callback(connection, notif):
      pass
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.KEYSTROKE_FILTER,
        callback,
        session=session,
        keystroke_monitor_request=kmr)

async def async_subscribe_to_screen_update_notification(connection, callback, session=None):
    """
    Registers a callback to be run when the screen contents change.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.ScreenUpdateNotification..
    :param session: The session to monitor, or None.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_SCREEN_UPDATE,
        callback,
        session=session)

async def async_subscribe_to_prompt_notification(connection, callback, session=None):
    """
    Registers a callback to be run when a shell prompt is received.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.PromptNotification.
    :param session: The session to monitor, or None.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_PROMPT,
        callback,
        session=session)

async def async_subscribe_to_location_change_notification(connection, callback, session=None):
    """
    Registers a callback to be run when the host or current directory changes.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.LocationChangeNotification.
    :param session: The session to monitor, or None.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_LOCATION_CHANGE,
        callback,
        session=session)

async def async_subscribe_to_custom_escape_sequence_notification(connection,
                                                                 callback,
                                                                 session=None):
    """
    Registers a callback to be run when a custom escape sequence is received.

    The escape sequence is OSC 1337 ; Custom=id=<identity>:<payload> ST

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.CustomEscapeSequenceNotification.
    :param session: The session to monitor, or None.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_CUSTOM_ESCAPE_SEQUENCE,
        callback,
        session=session)

async def async_subscribe_to_terminate_session_notification(connection, callback):
    """
    Registers a callback to be run when a session terminates.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.TerminateSessionNotification.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_TERMINATE_SESSION,
        callback,
        session=None)

async def async_subscribe_to_layout_change_notification(connection, callback):
    """
    Registers a callback to be run when the relationship between sessions, tabs,
    and windows changes.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.LayoutChangedNotification.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_LAYOUT_CHANGE,
        callback,
        session=None)

async def async_subscribe_to_focus_change_notification(connection, callback):
    """
    Registers a callback to be run when focus changes.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.FocusChangedNotification.

    :returns: A token that can be passed to unsubscribe.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_FOCUS_CHANGE,
        callback,
        session=None)

async def async_subscribe_to_broadcast_domains_change_notification(connection, callback):
    """
    Registers a callback to be run when the current broadcast domains change.

    See also: :meth:`iTerm2.App.parse_broadcast_domains`. Pass it `notification.broadcast_domains`.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and
      iterm2.api_pb2.BroadcastDomainsChangedNotification.
    """
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_BROADCAST_CHANGE,
        callback,
        session=None)

async def async_subscribe_to_server_originated_rpc_notification(connection, callback, name, arguments=[], timeout_seconds=5, defaults={}, role=RPC_ROLE_GENERIC, session_title_display_name=None, status_bar_component=None):
    """
    Registers a callback to be run when the server wants to invoke an RPC.

    You probably want to use :meth:`iterm2.Registration.async_register_rpc_handler`
    instead of this. It's a much higher level API.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and iterm2.api_pb2.ServerOriginatedRPCNotification.
    :param timeout_seconds: How long iTerm2 should wait for this function to return or `None` to use the default timeout.
    :param defaults: Gives default values. Names correspond to argument names in `arguments`. Values are in-scope variables at the callsite.
    :param role: Defines the special purpose of this RPC. If none, use `RPC_ROLE_GENERIC`.
    :param session_title_display_name: Used by the `RPC_ROLE_SESSION_TITLE` role to give the name of the function to show in preferences.

    :returns: A token that can be passed to unsubscribe.
    """
    rpc_registration_request = iterm2.api_pb2.RPCRegistrationRequest()
    rpc_registration_request.name = name
    if timeout_seconds is not None:
        rpc_registration_request.timeout = timeout_seconds
    args = []
    for arg_name in arguments:
        arg = iterm2.api_pb2.RPCRegistrationRequest.RPCArgumentSignature()
        arg.name = arg_name
        args.append(arg)
    rpc_registration_request.arguments.extend(args)
    rpc_registration_request.role = role

    if len(defaults) > 0:
        d = []
        for name in defaults:
            assert name in arguments, "Name for default '{}' not in arguments {}".format(name, arguments)
            path = defaults[name]
            argd = iterm2.api_pb2.RPCRegistrationRequest.RPCArgument()
            argd.name = name
            argd.path = path
            d.append(argd)

        rpc_registration_request.defaults.extend(d)

    if session_title_display_name is not None:
        rpc_registration_request.session_title_attributes.display_name = session_title_display_name
    elif status_bar_component is not None:
        status_bar_component.set_fields_in_proto(rpc_registration_request.status_bar_component_attributes)

    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_SERVER_ORIGINATED_RPC,
        callback,
        rpc_registration_request=rpc_registration_request)

async def async_subscribe_to_variable_change_notification(connection, callback, scope, name, identifier):
    """
    Registers a callback to be invoked when a variable changes.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: an :class:`Connection` and iterm2.api_pb2.VariableChangedNotification.
    :param scope: A :class:`VariableScopes` enumerated value.
    :param name: The name of the variable, a string.
    :param identifier: The identifier of the object (window, tab, or session) being monitored, or None for app.
    """
    # TODO: Support identifiers of "all"
    request = iterm2.api_pb2.VariableMonitorRequest()
    request.name = name
    request.scope = scope
    if identifier is not None:
        request.identifier = identifier
    else:
        request.identifier = ""
    key = (request.scope, request.identifier, request.name, iterm2.api_pb2.NOTIFY_ON_VARIABLE_CHANGE)
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_pb2.NOTIFY_ON_VARIABLE_CHANGE,
        callback,
        session=None,
        variable_monitor_request=request,
        key=key)

async def async_subscribe_to_profile_change_notification(connection, callback, guid):
    """
    Register a callback to be invoked when a profile changes.

    :param connection: A connected :class:`Connection`.
    :param callback: A coroutine taking two arguments: a :class:`Connection` and iterm2.api_pb2.ProfileChangedNotification.
    :parm guid: The guid to monitor. A string.
    """
    request = iterm2.api_pb2.ProfileChangeRequest()
    request.guid = guid
    key = (guid, iterm2.api_PB2.NOTIFY_ON_PROFILE_CHANGE)
    return await _async_subscribe(
        connection,
        True,
        iterm2.api_PB2.NOTIFY_ON_PROFILE_CHANGE,
        callback,
        session=None,
        profile_change_request=request,
        key=key)



## Private --------------------------------------------------------------------

def _string_rpc_registration_request(rpc):
    """Converts ServerOriginatedRPC or RPCSignature to a string."""
    if rpc is None:
        return None
    args = sorted(map(lambda x: x.name, rpc.arguments))
    return rpc.name + "(" + ",".join(args) + ")"

async def _async_subscribe(connection, subscribe, notification_type, callback, session=None, rpc_registration_request=None, keystroke_monitor_request=None, variable_monitor_request=None, key=None, profile_change_request=None):
    _register_helper_if_needed()
    transformed_session = session if session is not None else "all"

    # Register locally in case iTerm2 responds with an RPC immediately.
    # That is typical when registering a session title provider when a session is already open.
    if subscribe:
        if key:
            _register_notification_handler_impl(key, callback)
        else:
            _register_notification_handler(
                    session,
                    _string_rpc_registration_request(rpc_registration_request),
                    notification_type,
                    callback)

    response = await iterm2.rpc.async_notification_request(
        connection,
        subscribe,
        notification_type,
        transformed_session,
        rpc_registration_request,
        keystroke_monitor_request,
        variable_monitor_request,
        profile_change_request)
    status = response.notification_response.status
    status_ok = (status == iterm2.api_pb2.NotificationResponse.Status.Value("OK"))

    unregister = False
    if subscribe:
        already = (status == iterm2.api_pb2.NotificationResponse.Status.Value("ALREADY_SUBSCRIBED"))
        if status_ok or already:
            if key:
                return (key, callback)
            else:
                return ((session, notification_type), callback)
        else:
            # Uh oh, undo the registration.
            unregister = True
    else:
        # Unsubscribe
        if status_ok:
            unregister = True

    if unregister:
        if key:
            _unregister_notification_handler_impl(key, callback)
        else:
            _unregister_notification_handler(
                session,
                _string_rpc_registration_request(rpc_registration_request),
                notification_type,
                callback)

        if not subscribe and status_ok:
            # Normal code path for unsubscribe
            return

    raise SubscriptionException(iterm2.api_pb2.NotificationResponse.Status.Name(status))

def _register_helper_if_needed():
    if not hasattr(_register_helper_if_needed, 'haveRegisteredHelper'):
        _register_helper_if_needed.haveRegisteredHelper = True
        iterm2.connection.Connection.register_helper(_async_dispatch_helper)

async def _async_dispatch_helper(connection, message):
    handlers, sub_notification = _get_notification_handlers(message)
    for handler in handlers:
        assert handler is not None
        await handler(connection, sub_notification)

    if not handlers and message.notification.HasField('server_originated_rpc_notification'):
        # If we get an RPC we haven't registered for handle the error because
        # otherwise it has to time out. If you get here there is probably a bug.
        key, _sub_notification = _get_handler_key_from_notification(message.notification)
        exception = { "reason": "No such function: {} (key was {})".format(_string_rpc_registration_request(message.notification.server_originated_rpc_notification.rpc), key) }
        await iterm2.rpc.async_send_rpc_result(connection, message.notification.server_originated_rpc_notification.request_id, True, exception)

    return bool(handlers)

def _get_handler_key_from_notification(notification):
    key = None

    if notification.HasField('keystroke_notification'):
        key = (notification.keystroke_notification.session, iterm2.api_pb2.NOTIFY_ON_KEYSTROKE)
        notification = notification.keystroke_notification
    elif notification.HasField('screen_update_notification'):
        key = (notification.screen_update_notification.session,
               iterm2.api_pb2.NOTIFY_ON_SCREEN_UPDATE)
        notification = notification.screen_update_notification
    elif notification.HasField('prompt_notification'):
        key = (notification.prompt_notification.session, iterm2.api_pb2.NOTIFY_ON_PROMPT)
        notification = notification.prompt_notification
    elif notification.HasField('location_change_notification'):
        key = (notification.location_change_notification.session,
               iterm2.api_pb2.NOTIFY_ON_LOCATION_CHANGE)
        notification = notification.location_change_notification
    elif notification.HasField('custom_escape_sequence_notification'):
        key = (notification.custom_escape_sequence_notification.session,
               iterm2.api_pb2.NOTIFY_ON_CUSTOM_ESCAPE_SEQUENCE)
        notification = notification.custom_escape_sequence_notification
    elif notification.HasField('new_session_notification'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_NEW_SESSION)
        notification = notification.new_session_notification
    elif notification.HasField('terminate_session_notification'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_TERMINATE_SESSION)
        notification = notification.terminate_session_notification
    elif notification.HasField('layout_changed_notification'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_LAYOUT_CHANGE)
        notification = notification.layout_changed_notification
    elif notification.HasField('focus_changed_notification'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_FOCUS_CHANGE)
        notification = notification.focus_changed_notification
    elif notification.HasField('server_originated_rpc_notification'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_SERVER_ORIGINATED_RPC, _string_rpc_registration_request(notification.server_originated_rpc_notification.rpc))
    elif notification.HasField('broadcast_domains_changed'):
        key = (None, iterm2.api_pb2.NOTIFY_ON_BROADCAST_CHANGE)
    elif notification.HasField('variable_changed_notification'):
        key = (notification.variable_changed_notification.scope,
               notification.variable_changed_notification.identifier,
               notification.variable_changed_notification.name,
               iterm2.api_pb2.NOTIFY_ON_VARIABLE_CHANGE)
        notification = notification.variable_changed_notification
    elif notification.HasField('profile_changed_notification'):
        key = (notification.profile_changed_notification.guid,
                iterm2.api_pb2.NOTIFY_ON_PROFILE_CHANGE)
    return key, notification

def _get_notification_handlers(message):
    key, sub_notification = _get_handler_key_from_notification(message.notification)
    if key is None:
        return ([], None)

    fallback = (None, key[1])

    if key in _get_handlers():
        return (_get_handlers()[key], sub_notification)
    elif fallback in _get_handlers():
        return (_get_handlers()[fallback], sub_notification)
    return ([], None)

def _register_notification_handler(session, rpc_registration_request, notification_type, coro):
    assert coro is not None

    if rpc_registration_request is None:
        key = (session, notification_type)
    else:
        key = (session, notification_type, rpc_registration_request)
    _register_notification_handler_impl(key, coro)

def _register_notification_handler_impl(key, coro):
    if key in _get_handlers():
        _get_handlers()[key].append(coro)
    else:
        _get_handlers()[key] = [coro]

def _unregister_notification_handler(session, rpc_registration_request, notification_type, coro):
    assert coro is not None

    if rpc_registration_request is None:
        key = (session, notification_type)
    else:
        key = (session, notification_type, rpc_registration_request)
    _unregister_notification_handler_impl(key, coro)

def _unregister_notification_handler_impl(key, coro):
    if key in _get_handlers():
        if coro in _get_handlers()[key]:
            _get_handlers()[key].remove(coro)

class NewSessionMonitor:
    """Watches for the creation of new sessions.

      :param connection: The :class:`iterm2.Connection` to use.

       Example:

       .. code-block:: python

           app = await iterm2.async_get_app(connection)
           async with NewSessionMonitor(connection) as mon:
               while True:
                   session_id = await mon.async_get()
                   DoSomethingWithSession(app.get_session_by_id(session_id))

      """
    def __init__(self, connection):
        self.__connection = connection
        self.__queue = asyncio.Queue(loop=asyncio.get_event_loop())

    async def __aenter__(self):
        async def callback(_connection, message):
            """Called when a new session is created."""
            await self.__queue.put(message)

        self.__token = await async_subscribe_to_new_session_notification(
                self.__connection,
                callback)
        return self

    async def async_get(self):
        """
        Returns the new session ID.
        """
        result = await self.__queue.get()
        session_id = result.uniqueIdentifier
        return session_id

    async def __aexit__(self, exc_type, exc, _tb):
        await async_unsubscribe(self.__connection, self.__token)

