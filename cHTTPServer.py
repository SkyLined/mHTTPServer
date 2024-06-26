try: # mDebugOutput use is Optional
  from mDebugOutput import ShowDebugOutput, fShowDebugOutput;
except ModuleNotFoundError as oException:
  if oException.args[0] != "No module named 'mDebugOutput'":
    raise;
  ShowDebugOutput = lambda fx: fx; # NOP
  fShowDebugOutput = lambda x, s0 = None: x; # NOP

try: # m0SSL support is optional
  import mSSL as m0SSL;
except ModuleNotFoundError as oException:
  if oException.args[0] != "No module named 'mSSL'":
    raise;
  m0SSL = None;

from mHTTPConnection import cHTTPConnectionAcceptor, cHTTPResponse, cURL;
from mMultiThreading import cLock, cThread, cWithCallbacks;
from mNotProvided import \
    fAssertType, \
    fxGetFirstProvidedValue, \
    zNotProvided;

from .mExceptions import \
    acExceptions, \
    cHTTPInvalidMessageException, \
    cTCPIPConnectionDisconnectedException, \
    cTCPIPConnectionShutdownException, \
    cTCPIPDataTimeoutException;

# To turn access to data store in multiple variables into a single transaction, we will create locks.
# These locks should only ever be locked for a short time; if it is locked for too long, it is considered a "deadlock"
# bug, where "too long" is defined by the following value:
gnDeadlockTimeoutInSeconds = 1; # We're not doing anything time consuming, so this should suffice.

class cHTTPServer(cWithCallbacks):
  bSSLIsSupported = m0SSL is not None;
  n0DefaultTransactionTimeoutInSeconds = 10;
  n0DefaultIdleTimeoutInSeconds = 60;
  sbDefaultHost = cHTTPConnectionAcceptor.sbDefaultHost;
  
  @ShowDebugOutput
  def __init__(oSelf,
    ftxRequestHandler,
    sbzHost = zNotProvided, uzPortNumber = zNotProvided,
    o0SSLContext = None,
    n0zTransactionTimeoutInSeconds = zNotProvided,
    n0zIdleTimeoutInSeconds = zNotProvided,
  ):
    fAssertType("sbzHost", sbzHost, bytes, zNotProvided);
    fAssertType("uzPortNumber", uzPortNumber, int, zNotProvided);
    if m0SSL:
      fAssertType("o0SSLContext", o0SSLContext, m0SSL.cSSLContext, None);
    else:
      assert o0SSLContext is None, \
          "Cannot load module mSSL; o0SSLContext cannot be %s!" % repr(o0SSLContext);
    fAssertType("n0zTransactionTimeoutInSeconds", n0zTransactionTimeoutInSeconds, int, float, None, zNotProvided);
    fAssertType("n0zIdleTimeoutInSeconds", n0zIdleTimeoutInSeconds, int, float, None, zNotProvided);
    
    oSelf.__ftxRequestHandler = ftxRequestHandler;
    oSelf.__n0TransactionTimeoutInSeconds = fxGetFirstProvidedValue(n0zTransactionTimeoutInSeconds, oSelf.n0DefaultTransactionTimeoutInSeconds);
    oSelf.__n0IdleTimeoutInSeconds = fxGetFirstProvidedValue(n0zIdleTimeoutInSeconds, oSelf.n0DefaultIdleTimeoutInSeconds);
    
    oSelf.__oPropertyAccessTransactionLock = cLock(
      "%s.__oPropertyAccessTransactionLock" % oSelf.__class__.__name__,
      n0DeadlockTimeoutInSeconds = gnDeadlockTimeoutInSeconds
    );
    
    oSelf.__aoConnections = [];
    oSelf.__aoConnectionThreads = [];
    
    oSelf.__bStopping = False;
    oSelf.__oTerminatedLock = cLock(
      "%s.__oTerminatedLock" % oSelf.__class__.__name__,
      bLocked = True
    );
    
    oSelf.fAddEvents(
      "connection from client received",
      "idle timeout",
      "bytes read", "bytes written",
      "request error", "request received",
      "response error", "response sent",
      "request received and response sent",
      "connection from client terminated",
      "terminated"
    );
    
    oSelf.__oConnectionAcceptor = cHTTPConnectionAcceptor(
      fNewConnectionHandler = oSelf.__fHandleNewConnection,
      sbzHost = sbzHost,
      uzPortNumber = uzPortNumber,
      o0SSLContext = o0SSLContext,
      n0zSecureTimeoutInSeconds = oSelf.__n0TransactionTimeoutInSeconds,
    );
    oSelf.__oConnectionAcceptor.fAddCallback("terminated", oSelf.__HandleTerminatedCallbackFromConnectionAcceptor);
  
  @property
  def sbHost(oSelf):
    return oSelf.__oConnectionAcceptor.sbHost;
  @property
  def uPortNumber(oSelf):
    return oSelf.__oConnectionAcceptor.uPortNumber;
  @property
  def o0SSLContext(oSelf):
    return oSelf.__oConnectionAcceptor.o0SSLContext;
  @property
  def bSecure(oSelf):
    return oSelf.__oConnectionAcceptor.bSecure;
  @property
  def asbIPAddresses(oSelf):
    return oSelf.__oConnectionAcceptor.asbIPAddresses;
  @property
  def bTerminated(oSelf):
    return not oSelf.__oTerminatedLock.bLocked;
  @property
  def oURL(oSelf):
    return oSelf.foGetURL();
  
  def foGetURL(oSelf, sb0Path = None, sb0Query = None, sb0Fragment = None):
    return cURL(
      sbProtocol = b"https" if oSelf.__oConnectionAcceptor.bSecure else b"http",
      sbHost = oSelf.sbHost,
      u0PortNumber = oSelf.uPortNumber,
      sb0Path = sb0Path,
      sb0Query = sb0Query,
      sb0Fragment = sb0Fragment
    );
  
  def foGetURLForRequest(oSelf, oRequest):
    return oSelf.oURL.foFromRelativeBytesString(oRequest.sbURL);
  
  @ShowDebugOutput
  def __fCheckForTermination(oSelf, bMustBeTerminated = False):
    oSelf.__oPropertyAccessTransactionLock.fAcquire();
    try:
      if oSelf.bTerminated:
        return fShowDebugOutput("Already terminated");
      if not oSelf.__bStopping:
        return fShowDebugOutput("Not stopping");
      if not oSelf.__oConnectionAcceptor.bTerminated:
        return fShowDebugOutput("We may still be accepting connections.");
      if len(oSelf.__aoConnections) > 0:
        fShowDebugOutput("There %s %d open connection%s:" % (
          "is" if len(oSelf.__aoConnections) == 1 else "are",
          len(oSelf.__aoConnections),
          "" if len(oSelf.__aoConnections) == 1 else "s",
        ));
        for oConnection in oSelf.__aoConnections:
          fShowDebugOutput("  %s" % oConnection);
        return;
      if len(oSelf.__aoConnectionThreads) > 0:
        fShowDebugOutput("There are %d running connection threads:" % len(oSelf.__aoConnections));
        for oConnectionThread in oSelf.__aoConnectionThreads:
          fShowDebugOutput("  %s" % oConnectionThread);
        return;
      oSelf.__oTerminatedLock.fRelease();
    finally:
      oSelf.__oPropertyAccessTransactionLock.fRelease();
    fShowDebugOutput("%s terminating." % oSelf.__class__.__name__);
    oSelf.fFireCallbacks("terminated");
  
  def __HandleTerminatedCallbackFromConnectionAcceptor(oSelf, oConnectionAcceptor):
    oSelf.__fCheckForTermination();
  
  @ShowDebugOutput
  def fStop(oSelf):
    if oSelf.bTerminated:
      return fShowDebugOutput("Already terminated");
    if oSelf.__bStopping:
      return fShowDebugOutput("Already stopping");
    fShowDebugOutput("Stopping...");
    # Prevent any new requests from being processed.
    oSelf.__bStopping = True;
    # Prevent any new connections from being accepted.
    oSelf.__oConnectionAcceptor.fStop();
    # Get a list of existing connections that also need to be stopped.
    oSelf.__oPropertyAccessTransactionLock.fAcquire();
    try:
      aoConnections = oSelf.__aoConnections[:];
    finally:
      oSelf.__oPropertyAccessTransactionLock.fRelease();
    if aoConnections:
      fShowDebugOutput("Stopping %d open connections..." % len(aoConnections));
      for oConnection in aoConnections:
        oConnection.fStop();
  
  @ShowDebugOutput
  def fTerminate(oSelf):
    if oSelf.bTerminated:
      return fShowDebugOutput("Already terminated");
    fShowDebugOutput("Terminating...");
    # Prevent any new connections from being accepted.
    oSelf.__oConnectionAcceptor.fTerminate();
    # Prevent any new connections from being accepted.
    oSelf.__bStopping = True;
    # Get a list of existing connections that also need to be terminated.
    oSelf.__oPropertyAccessTransactionLock.fAcquire();
    try:
      aoConnections = oSelf.__aoConnections[:];
    finally:
      oSelf.__oPropertyAccessTransactionLock.fRelease();
    if aoConnections:
      fShowDebugOutput("Terminating %d open connections..." % len(aoConnections));
      for oConnection in aoConnections:
        oConnection.fTerminate();
  
  @ShowDebugOutput
  def fWait(oSelf):
    return oSelf.__oTerminatedLock.fWait();
  @ShowDebugOutput
  def fbWait(oSelf, nTimeoutInSeconds):
    return oSelf.__oTerminatedLock.fbWait(nTimeoutInSeconds);
  
  @ShowDebugOutput
  def __fHandleNewConnection(oSelf, oConnectionAcceptor, oConnection):
    oConnection.fAddCallbacks({
      "bytes read": lambda oConnection, sbBytesRead: oSelf.fFireCallbacks(
        "bytes read", oConnection, sbBytesRead,
      ),
      "bytes written": lambda oConnection, sbBytesWritten: oSelf.fFireCallbacks(
        "bytes written", oConnection, sbBytesWritten,
      ),
    });
    fShowDebugOutput("New connection %s..." % (oConnection,));
    oSelf.fFireCallbacks("connection from client received", oConnection);
    oConnection.fAddCallbacks({
      "request received": lambda oConnection, oRequest: oSelf.fFireCallbacks(
        "request received", oConnection, oRequest,
      ),
      "response sent":lambda oConnection, oResponse: oSelf.fFireCallbacks(
        "response sent", oConnection, oResponse,
      ),
      "request received and response sent": lambda oConnection, oRequest, oResponse: oSelf.fFireCallbacks(
        "request received and response sent", oConnection, oRequest, oResponse,
      ),
    });
    oSelf.__oPropertyAccessTransactionLock.fAcquire();
    try:
      assert not oSelf.bTerminated, \
        "Received a new connection after we've terminated!?";
      if oSelf.__bStopping:
        fShowDebugOutput("Stopping connection since we are stopping...");
        bHandleConnection = False;
      else:
        oThread = cThread(oSelf.__fConnectionThread, oConnection);
        oSelf.__aoConnections.append(oConnection);
        oSelf.__aoConnectionThreads.append(oThread);
        bHandleConnection = True;
    finally:
      oSelf.__oPropertyAccessTransactionLock.fRelease();
    if bHandleConnection:
      oConnection.fAddCallback("terminated", oSelf.__fHandleTerminatedCallbackFromConnection);
      oThread.fStart();
    else:
      oConnection.fStop();
  
  def __fHandleTerminatedCallbackFromConnection(oSelf, oConnection):
    assert oConnection in oSelf.__aoConnections, \
        "What!?";
    oSelf.__oPropertyAccessTransactionLock.fAcquire();
    try:
      oSelf.__aoConnections.remove(oConnection);
    finally:
      oSelf.__oPropertyAccessTransactionLock.fRelease();
    oSelf.fFireCallbacks("connection from client terminated", oConnection);
    oSelf.__fCheckForTermination();
  
  @ShowDebugOutput
  def __fConnectionThread(oSelf, oConnection):
    oThread = cThread.foGetCurrent();
    try:
      while not oSelf.__bStopping:
        # Wait for a request if needed and start a transaction, handle errors.
        try:
          fShowDebugOutput("Waiting for request from %s..." % oConnection);
          oConnection.fWaitUntilBytesAreAvailableForReadingAndStartTransaction(
            n0WaitTimeoutInSeconds = oSelf.__n0IdleTimeoutInSeconds,
            n0TransactionTimeoutInSeconds = oSelf.__n0TransactionTimeoutInSeconds,
          );
        except cTCPIPConnectionShutdownException:
          fShowDebugOutput("Connection %s was shut down." % oConnection);
          break;
        except cTCPIPConnectionDisconnectedException:
          fShowDebugOutput("Connection %s was disconnected." % oConnection);
          break;
        except cTCPIPDataTimeoutException as oException:
          fShowDebugOutput("Wait for request from %s timed out: %s." % (oConnection, oException));
          oSelf.fFireCallbacks("idle timeout", oConnection);
          oConnection.fStop();
          break;
        # At this point we have started a transaction that we MUST end.
        try:
          # Read request, handle errors.
          fShowDebugOutput("Reading request from %s..." % oConnection);
          try:
            oRequest = oConnection.foReceiveRequest();
          except cTCPIPConnectionShutdownException as oException:
            fShowDebugOutput("Shutdown while reading request from %s: %s." % (oConnection, oException));
            oSelf.fFireCallbacks("request error", oConnection, oException);
            oConnection.fDisconnect();
            break;
          except cTCPIPConnectionDisconnectedException as oException:
            fShowDebugOutput("Disconnected while reading request from %s: %s." % (oConnection, oException));
            oSelf.fFireCallbacks("request error", oConnection, oException);
            break;
          except cHTTPInvalidMessageException as oException:
            fShowDebugOutput("Invalid request from %s: %s." % (oConnection, oException));
            oSelf.fFireCallbacks("request error", oConnection, oException);
            oConnection.fTerminate();
            break;
          except cTCPIPDataTimeoutException as oException:
            fShowDebugOutput("Reading request from %s timed out: %s." % (oConnection, oException));
            oSelf.fFireCallbacks("request error", oConnection, oException);
            oConnection.fTerminate();
            break;
          # Have the request handler generate a response to the request object
          (
            o0Response,
            bDisconnectAfterOptionallySendingResponse,
            f0NextConnectionHandler
          ) = oSelf.__ftxRequestHandler(oSelf, oConnection, oRequest);
          assert o0Response is None or isinstance(o0Response, cHTTPResponse), \
              "The request handler function returned an invalid o0Response: %s" % repr(o0Response);
          assert f0NextConnectionHandler is None or callable(f0NextConnectionHandler), \
              "The request handler function returned an invalid f0NextConnectionHandler: %s" % repr(o0Response);
          
          if o0Response:
            oResponse = o0Response;
            if oSelf.__bStopping:
              oResponse.oHeaders.fbReplaceHeadersForNameAndValue(b"Connection", b"Close");
            # Send response, handle errors
            fShowDebugOutput("Sending response %s to %s..." % (oResponse, oConnection));
            try:
              oConnection.fSendResponse(oResponse);
            except Exception as oException:
              if isinstance(oException, cTCPIPConnectionShutdownException):
                fShowDebugOutput("Connection %s was shut down while sending response %s." % (oConnection, oResponse));
                if oConnection.bConnected:
                  fShowDebugOutput("Closing connection because it was shut down...");
              elif isinstance(oException, cTCPIPConnectionDisconnectedException):
                fShowDebugOutput("Connection %s was disconnected while sending response %s." % (oConnection, oResponse));
              elif isinstance(oException, cTCPIPDataTimeoutException):
                fShowDebugOutput("Sending response to %s timed out." % (oConnection, oException));
                if oConnection.bConnected:
                  fShowDebugOutput("Closing connection because of a response timeout...");
              else:
                raise;
              oSelf.fFireCallbacks("response error", oConnection, oException, oRequest, oResponse);
              break;
            if oSelf.__bStopping:
              if oConnection.bConnected: 
                fShowDebugOutput("Closing connection to stop server...");
              break;
            if bDisconnectAfterOptionallySendingResponse:
              fShowDebugOutput("Closing connection per request handler...");
              break;
          else:
            # (None, False, None) makes no sense:
            assert bDisconnectAfterOptionallySendingResponse, \
                "Request handler did not tell us what to do.";
            if oConnection.bConnected: 
              fShowDebugOutput("Closing connection without response per request handler...");
            break;
        finally:
          # End the transaction
          oConnection.fEndTransaction();
        if f0NextConnectionHandler:
          fShowDebugOutput("Stopped handling requests at the request of the request handler");
          fShowDebugOutput("Passing the connection to the next connection handler.");
          f0NextConnectionHandler(oConnection);
          if oConnection.bConnected: 
            fShowDebugOutput("Closing connection because the next connection handler is finished...");
          break;
    finally:
      try:
        oConnection.fStartTransaction(
          n0TimeoutInSeconds = 0,
        );
        try:
          oConnection.fDisconnect();
        finally:
          oConnection.fEndTransaction();
      except cTCPIPConnectionDisconnectedException:
        pass;
      oSelf.__oPropertyAccessTransactionLock.fAcquire();
      try:
        oSelf.__aoConnectionThreads.remove(oThread);
      finally:
        oSelf.__oPropertyAccessTransactionLock.fRelease();
      fShowDebugOutput("Connection thread terminated");
      oSelf.__fCheckForTermination();
  
  def fasGetDetails(oSelf):
    # This is done without a property lock, so race-conditions exist and it
    # approximates the real values.
    if oSelf.bTerminated:
      return ["terminated"];
    return [s for s in [
        str(oSelf.oURL),
        "stopping" if oSelf.__bStopping else None,
        "%s connections" % (len(oSelf.__aoConnections) or "no"),
        "%s connection threads" % (len(oSelf.__aoConnectionThreads) or "no"),
    ] if s];
  
  def __repr__(oSelf):
    sModuleName = ".".join(oSelf.__class__.__module__.split(".")[:-1]);
    return "<%s.%s#%X|%s>" % (sModuleName, oSelf.__class__.__name__, id(oSelf), "|".join(oSelf.fasGetDetails()));
  
  def __str__(oSelf):
    return "%s#%X{%s}" % (oSelf.__class__.__name__, id(oSelf), ", ".join(oSelf.fasGetDetails()));

for cException in acExceptions:
  setattr(cHTTPServer, cException.__name__, cException);