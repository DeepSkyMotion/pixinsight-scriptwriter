// __SLUG___v__N__GUI.js - dialog only. Reads/writes PSWParameters, never processes pixels.
// V8 engine style: ES6 class extends Dialog, enums as Namespace.Value (FrameStyle.Box ...).

var PSWDialog = class extends Dialog
{
   constructor( params, parent )
   {
      super( parent );

      this.params = params;
      let self = this;
      let labelWidth = this.font.width( "Amount:" ) + this.font.width( 'M' );

      this.helpLabel = new Label( this );
      this.helpLabel.frameStyle = FrameStyle.Box;
      this.helpLabel.margin = 6;
      this.helpLabel.wordWrapping = true;
      this.helpLabel.useRichText = true;
      this.helpLabel.text = "<p><b>" + PSW_TITLE + "</b> &mdash; SHORT ENGLISH HELP TEXT.</p>";

      this.amountControl = new NumericControl( this );
      this.amountControl.label.text = "Amount:";
      this.amountControl.label.minWidth = labelWidth;
      this.amountControl.setRange( 0, 1 );
      this.amountControl.slider.setRange( 0, 1000 );
      this.amountControl.setPrecision( 3 );
      this.amountControl.setValue( params.amount );
      this.amountControl.toolTip = "<p>ENGLISH TOOLTIP.</p>";
      this.amountControl.onValueUpdated = function( value ) { self.params.amount = value; };

      this.okButton = new PushButton( this );
      this.okButton.text = "OK";
      this.okButton.icon = this.scaledResource( ":/icons/ok.png" );
      this.okButton.onClick = function() { self.ok(); };

      this.cancelButton = new PushButton( this );
      this.cancelButton.text = "Cancel";
      this.cancelButton.icon = this.scaledResource( ":/icons/cancel.png" );
      this.cancelButton.onClick = function() { self.cancel(); };

      this.buttonsSizer = new HorizontalSizer;
      this.buttonsSizer.spacing = 6;
      this.buttonsSizer.addStretch();
      this.buttonsSizer.add( this.okButton );
      this.buttonsSizer.add( this.cancelButton );

      this.sizer = new VerticalSizer;
      this.sizer.margin = 8;
      this.sizer.spacing = 8;
      this.sizer.add( this.helpLabel );
      this.sizer.add( this.amountControl );
      this.sizer.add( this.buttonsSizer );

      this.windowTitle = PSW_TITLE;
      this.setScaledMinWidth( 420 );
      this.adjustToContents();
   }
};
