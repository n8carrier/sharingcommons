from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel
from src.accounts.models import UserAccount
from src.books.models import ItemCopy,Item


class Action(polymodel.PolyModel):
	useraccount = ndb.KeyProperty(kind=UserAccount)
	created = ndb.DateTimeProperty(auto_now_add=True)
	text = "This is the default text, it should never show up"
	can_accept = False 
	accept_text = "Accept"
	can_reject = False
	reject_text = "Reject" 
	
	def confirm(self):
		print "CONFIRMED"
	
	def reject(self):
		print "REJECT"
		
	def cleanup(self):
		self.key.delete()


"""
ACTION SUBCLASS TEMPLATE

class MyCustomAction(Action):
	# put any custom attributes here
	text = "Put whatever text here that needs to be displayed to the user"
	can_accept = True # or False if there is no accept option
	accept_text = "Accept" # this is what the button should say when accepting
	can_reject = True # or False if there is no reject option
	reject_text = "Reject" # this is that the button should say when rejecting
	
	def confirm(self):
		# do whatever stuff should be done when the user confirms
	
	def reject(self):
		# do whatever stuff should be done when the user rejects


"""


class ConnectionRequest(Action):
	connection = ndb.KeyProperty(kind=UserAccount)
	
	@property
	def text(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		return "%s has requested to connect" %(other.name)
		
	can_accept = True 
	accept_text = "Accept"
	can_reject = True
	reject_text = "Deny" 
	
	def confirm(self):
		invitee = UserAccount.query(UserAccount.key==self.connection).get()
		invited = UserAccount.query(UserAccount.key==self.useraccount).get()
		invited.add_connection(invitee)
		self.cleanup()
		return "You have accepted a connection request from %s" %(invitee.name)
	
	def reject(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		self.cleanup()
		return "You have rejected a connection request from %s" %(other.name)


class RequestToBorrow(Action):
	connection = ndb.KeyProperty(kind=UserAccount)
	item = ndb.KeyProperty(kind=ItemCopy)
	
	@property
	def text(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		return "%s has requested to borrow '%s'" %(other.name,item.title)
		
	can_accept = True 
	accept_text = "Confirm Checkout"
	can_reject = True
	reject_text = "Deny"
	
	def confirm(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		
		due_date = None
		cur_user = UserAccount.query(UserAccount.key==self.useraccount).get()
		cur_user.lend_book(int(bookcopy.key.id()), int(other.key.id()), due_date)
		
		self.cleanup()
		
		otherAction = WaitingToBorrow.query(WaitingToBorrow.item == bookcopy.key and WaitingToBorrow.useraccount == other.key).get()
		otherAction.cleanup()
		
		return "You have agreed to lend %s to %s" %(item.title,other.name)
	
	def reject(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		self.cleanup()

		otherAction = WaitingToBorrow.query(WaitingToBorrow.item == bookcopy.key and WaitingToBorrow.useraccount == other.key).get()
		otherAction.cleanup()
		
		return "You have denied %s permission to borrow %s" %(other.name,item.title)
		


class WaitingToBorrow(Action):
	connection = ndb.KeyProperty(kind=UserAccount)
	item = ndb.KeyProperty(kind=ItemCopy)
	
	@property
	def text(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		return "You have requested to borrow '%s' from %s" %(item.title,other.name)
		
	can_accept = False 
	accept_text = "Allow"
	can_reject = True
	reject_text = "Withdraw Request" 
	
	def confirm(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		print "You have accepted a connection request from %s" %(other.name)
		#self.cleanup()
	
	def reject(self):
		other = UserAccount.query(UserAccount.key==self.connection).get()
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		self.cleanup()
		
		otherAction = RequestToBorrow.query(RequestToBorrow.item == bookcopy.key and RequestToBorrow.useraccount == other.key).get()
		otherAction.cleanup()
		
		return "Request cancelled"


class ConfirmReturn(Action):
	item = ndb.KeyProperty(kind=ItemCopy)
	
	@property
	def text(self):
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		other = UserAccount.query(UserAccount.key==bookcopy.borrower).get()
		item = Item.query(Item.key==bookcopy.item).get()
		return "%s reported checking in '%s'" %(other.name,item.title)
		
	can_accept = True 
	accept_text = "Confirm"
	can_reject = True
	reject_text = "Deny"
	
	def confirm(self):
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		other = UserAccount.query(UserAccount.key==bookcopy.borrower).get()
		item = Item.query(Item.key==bookcopy.item).get()
		bookcopy.return_book()
		bookcopy.put()
		self.cleanup()
		return "%s has been returned to your library" %(item.title)
	
	def reject(self):
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		other = UserAccount.query(UserAccount.key==bookcopy.borrower).get()
		item = Item.query(Item.key==bookcopy.item).get()
		self.cleanup()
		return "Recorded that %s didn't return %s" %(other.name,item.title)


class DueDateExtension(Action):
	item = ndb.KeyProperty(kind=ItemCopy)
	due_date = ndb.DateProperty()
	
	@property
	def text(self):
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		other = UserAccount.query(UserAccount.key==bookcopy.borrower).get()
		item = Item.query(Item.key==bookcopy.item).get()
		return "%s wants to extend the due date of '%s' to %s?" %(other.name,item.title,str(self.due_date))
		
	can_accept = True 
	accept_text = "Allow"
	can_reject = True
	reject_text = "No" 
	
	def confirm(self):
		bookcopy = ItemCopy.query(ItemCopy.key==self.item).get()
		item = Item.query(Item.key==bookcopy.item).get()
		bookcopy.update_due_date(self.due_date)
		bookcopy.put()
		self.cleanup()
		return "%s has been extended to %s" %(item.title,str(self.due_date))
	
	def reject(self):
		self.cleanup()
		return "Extension rejected"




