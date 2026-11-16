module.exports = (req, res) => {
  if (req.query.next === 'account') return res.redirect('/account');
  res.redirect('/');
};
