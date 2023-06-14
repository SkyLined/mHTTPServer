import urllib.request;

from mHTTPServer import cHTTPServer;
from mConsole import oConsole;

def ftxRequestHandler(
  oHTTPServer,
  oConnection,
  oRequest,
):
  global guRequestsRecieved;
  guRequestsRecieved += 1;
  oConsole.fOutput("Client->Server oRequest: ", str(oRequest));
  oResponse = oConnection.foCreateResponse(s0Data = "Hello, world!");
  oConsole.fOutput("Client<-Server oResponse: ", str(oResponse));
  return (oResponse, None);

def fTestServer(
  o0CertificateAuthority,
  oServerURL,
  nEndWaitTimeoutInSeconds,
  f0LogEvents,
):
  global guRequestsRecieved;
  guRequestsRecieved = 0;
  if oServerURL.bSecure:
    assert o0CertificateAuthority, \
        "Cannot test a secure server (%s) without a certificate authority!" % oServerURL;
    oConsole.fOutput("\u2500\u2500\u2500\u2500 Creating a cSSLContext instance for %s... " % repr(oServerURL.sbHostname), sPadding = "\u2500");
    o0ServerSideSSLContext = o0CertificateAuthority.fo0GetServersideSSLContextForHostname(oServerURL.sbHostname);
    assert o0ServerSideSSLContext, \
        "No Certificate for hostname %s has been created using the Certificate Authority!" % repr(oServerURL.sbHostname);
    oConsole.fOutput("* o0ServerSideSSLContext for ", str(oServerURL.sbHostname, 'latin1'), ": ", str(o0ServerSideSSLContext));
    o0ClientSideSSLContext = o0CertificateAuthority.fo0GetClientSSLContextForHostname(oServerURL.sbHostname);
    assert o0ServerSideSSLContext, \
        "No Certificate for hostname %s has been created using the Certificate Authority!" % repr(oServerURL.sbHostname);
    oConsole.fOutput("* o0ClientSideSSLContext for ", str(oServerURL.sbHostname, 'latin1'), ": ", str(o0ClientSideSSLContext));
    o0ClientSidePythonSSLContext = o0ClientSideSSLContext.oPythonSSLContext;
  else:
    o0ServerSideSSLContext = None;
    o0ClientSidePythonSSLContext = None;
  oConsole.fOutput("\u2500\u2500\u2500\u2500 Creating a cHTTPServer instance at %s... " % oServerURL, sPadding = "\u2500");
  oHTTPServer = cHTTPServer(ftxRequestHandler, oServerURL.sbHostname, oServerURL.uPortNumber, o0ServerSideSSLContext);
  if f0LogEvents: f0LogEvents(oHTTPServer, "oHTTPServer");
  oConsole.fOutput("\u2500\u2500\u2500\u2500 Making a first test request to %s... " % oServerURL, sPadding = "\u2500");
  sServerURL = str(oServerURL.sbAbsolute, "ascii", "strict");
  oResponse = urllib.request.urlopen(sServerURL, context = o0ClientSidePythonSSLContext);
  assert guRequestsRecieved == 1, \
      "The server was expected to have received 1 request, but got %d instead" % guRequestsRecieved;
  oConsole.fOutput(repr(oResponse));
  oConsole.fOutput("\u2500\u2500\u2500\u2500 Making a second test request to %s... " % oServerURL, sPadding = "\u2500");
  oResponse = urllib.request.urlopen(sServerURL, context = o0ClientSidePythonSSLContext);
  assert guRequestsRecieved == 2, \
      "The server was expected to have received 2 requests, but got %d instead" % guRequestsRecieved;
  oConsole.fOutput(repr(oResponse));
  oConsole.fOutput("\u2500\u2500\u2500\u2500 Stopping the cHTTPServer instance at %s... " % oServerURL, sPadding = "\u2500");
  oHTTPServer.fStop();
  assert oHTTPServer.fbWait(nEndWaitTimeoutInSeconds), \
      "cHTTPServer instance did not stop in time";
  oConsole.fOutput("\u2500\u2500\u2500\u2500 Stopping the cHTTPClient instance... ", sPadding = "\u2500");
