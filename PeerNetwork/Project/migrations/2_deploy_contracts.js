const DataTransfer = artifacts.require("DataTransfer");

module.exports = function (deployer) {
  deployer.deploy(DataTransfer);
};
