// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DataTransfer {
    struct Request {
        address requester;
        address target; // New: Target peer address
        string dbQuery;
        bool fulfilled;
        string response;
    }

    mapping(uint => Request) public requests;
    uint public nextRequestId = 1;


    event RequestCreated(
        uint indexed requestId,
        address indexed requester,
        address indexed target,
        string dbQuery
    );

    event ResponseSent(
        uint indexed requestId,
        address indexed responder,
        string response
    );

    function createRequest(address _target, string calldata _dbQuery) external returns (uint) {
        uint requestId = nextRequestId++;
        requests[requestId] = Request({
            requester: msg.sender,
            target: _target,
            dbQuery: _dbQuery,
            fulfilled: false,
            response: ""
        });
        emit RequestCreated(requestId, msg.sender, _target, _dbQuery);
        return requestId;
    }

    function submitResponse(uint _requestId, string calldata _response) external {
        Request storage req = requests[_requestId];
        require(!req.fulfilled, "Request already fulfilled");
        req.fulfilled = true;
        req.response = _response;
        emit ResponseSent(_requestId, msg.sender, _response);
    }

    function getRequest(uint _requestId) external view returns (
        address requester,
        address target,
        string memory dbQuery,
        bool fulfilled,
        string memory response
    ) {
        Request storage req = requests[_requestId];
        return (req.requester, req.target, req.dbQuery, req.fulfilled, req.response);
    }
}
