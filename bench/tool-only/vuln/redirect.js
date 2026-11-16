module.exports = (req, res) => {
  res.redirect(req.query.next);
};
