cHTTPServer
===========
`cHTTPServer` is a Python class that can be used to create a HTTP/1.0&1.1
server. SSL support is optional; it is available if the `mSSL` module is
available.

`cHTTPServer` accepts connections and parses requests and will call a request
handler function provided in the arguments when it is instantiated for each
request. This function is passed three arguments:
1) The `cHTTPServer` object,
2) A `cHTTPConnection` object representing the connection to the client,
3) A `cHTTPRequest` object representing the request sent by the client.
The funtcion should return a tuple with two value:
1) A `cHTTPResponse` object representing the response to be sent to the client,
2) A boolean indicating whether the server can continue to use the connection
   after sending the response. If True, the server will continue to accept
   requests on this connection. If False, the server will no longer read or
   write to the connection. This can be useful if a HTTP request is used to
   switch to a different protocol on the connection, e.g. a WebSocket or a
   proxy CONNECT request.
