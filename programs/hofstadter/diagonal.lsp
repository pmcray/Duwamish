; =====================================================================
;  CONTRACROSTIPUNCTUS: every record player has a record it cannot play.
;
;  In Goedel, Escher, Bach the Crab keeps buying better phonographs, and
;  the Tortoise keeps bringing records that shatter them.  Turing's
;  version: no program can decide, for every program, whether it halts.
;
;  Here is a would-be oracle, HALTS?, that is as honest as it can be: it
;  runs the program in M-EVAL with a budget of steps, and says T if the
;  program finished within the budget.  It is right about FACT, right
;  about an endless loop -- and wrong about CONTRARY, a program built to
;  ask the oracle about itself and then do the opposite.  Raising the
;  budget does not help: CONTRARY's own simulation of the oracle always
;  needs more steps than the oracle has.
;
;  Load mceval.lsp first (see jobs/hofstadter.job).
; =====================================================================
(echo nil)
(install mc-source)
(define *m-global* (prims))
(define *depth* 0)
(define budget 200)

(define (halts? expr)
  (progn
    (cond ((= *depth* 0) (setq *fuel* budget)))
    (setq *depth* (+ *depth* 1))
    (m-run expr)
    (setq *depth* (- *depth* 1))
    (let ((ok (> *fuel* 0)))
      (progn (cond ((= *depth* 0) (setq *fuel* nil)))
             ok))))

; the oracle is available to the programs it judges
(m-setq 'halts? (cons 'prim halts?))
(m-run fact-source)
(m-run '(define (spin n) (spin n)))
(m-run '(define (contrary) (if (halts? '(contrary)) (spin 1) 'i-halted)))

(define (verdict x) (cond (x "halts") (else "runs forever")))

(define (trial b)
  (progn
    (setq budget b)
    (prin1 "budget ") (prin1 b) (print " steps:")
    (prin1 "   oracle on (FACT 3):     ") (print (verdict (halts? '(fact 3))))
    (prin1 "   oracle on (SPIN 1):     ") (print (verdict (halts? '(spin 1))))
    (prin1 "   oracle on (CONTRARY):   ") (print (verdict (halts? '(contrary))))
    (prin1 "   but (CONTRARY) returns  ") (print (m-run '(contrary)))
    (terpri)))

(print "CONTRACROSTIPUNCTUS -- a halting oracle, and the record that breaks it")
(terpri)
(trial 200)
(trial 600)
(print "Whatever the budget, CONTRARY asks the oracle about itself, hears")
(print "runs forever, and promptly halts.  An oracle that said halts would")
(print "be wrong the other way.  For every record player, a record it cannot")
(print "play: Turing's theorem, and the heart of Goedel's.")
